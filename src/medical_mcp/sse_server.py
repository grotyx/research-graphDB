"""Medical KAG MCP Server - SSE Transport with Multi-User Support (v7.16.0).

외부에서 HTTP로 접속할 수 있는 SSE 기반 MCP 서버.
사용자별 데이터 분리를 지원하며, 연결 안정성이 개선되었습니다.

Usage:
    # 권장 실행 방법
    python -m medical_mcp.sse_server --port 8000

    # 또는 래퍼 스크립트
    python scripts/run_mcp_sse.py --port 8000

    # 클라이언트에서 접속:
    # SSE endpoint: http://localhost:8000/sse?user=kim
    # 또는 헤더: X-User-ID: kim

사용자 설정:
    1. URL 파라미터: /sse?user=kim
    2. HTTP 헤더: X-User-ID: kim
    3. 미지정 시: system (모든 문서 접근)

데이터 분리:
    - owner: 문서 소유자 (예: kim, park, system)
    - shared: True면 모든 사용자 접근 가능
    - system 사용자는 모든 문서에 접근 가능

Endpoints:
    GET  /sse         - SSE connection (add ?user=<id> for multi-user)
    POST /messages    - MCP message handling
    GET  /health      - Health check with connection stats
    GET  /ping        - Simple ping
    GET  /tools       - List available MCP tools
    GET  /users       - List registered users
    POST /users/add   - Add new user (admin only)
    GET  /connections - Connection statistics
    POST /reset       - Reset server cache (reconnection support)
    POST /restart     - Restart Neo4j connection

v7.16.0 (2026-01-26):
    - SSE 서버 통합: run_mcp_sse.py → sse_server.py 래퍼로 변환
    - scripts/run_mcp_sse.py는 이 파일의 wrapper로 동작
    - 코드 중복 제거 및 유지보수성 향상

v7.14.2 개선사항:
    - /reset 엔드포인트 추가 (서버 캐시 초기화, 재연결 지원)
    - /restart 엔드포인트 추가 (Neo4j 연결 재설정)
    - 연결 실패 시 자동 복구 로직 강화
    - 초기화 미완료 요청 처리 개선

v7.13.1 개선사항:
    - Heartbeat 추가 (30초 간격)
    - 연결 상태 모니터링
    - 타임아웃 설정 개선
    - 에러 복구 강화
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Optional, Dict
from contextlib import asynccontextmanager

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from medical_mcp.medical_kag_server import MedicalKAGServer, create_mcp_server

try:
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import JSONResponse, Response
    from starlette.requests import Request
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    import uvicorn
    SSE_AVAILABLE = True
except ImportError as e:
    SSE_AVAILABLE = False
    IMPORT_ERROR = str(e)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# 설정
# ============================================
HEARTBEAT_INTERVAL = 30  # 초
CONNECTION_TIMEOUT = 300  # 5분 유휴 타임아웃
MAX_RECONNECT_ATTEMPTS = 3

# 등록된 사용자 목록 (실제 환경에서는 DB나 설정 파일로 관리)
REGISTERED_USERS = {
    "system": {"name": "System", "role": "admin"},
    "kim": {"name": "Kim", "role": "user"},
    "park": {"name": "Park", "role": "user"},
    "lee": {"name": "Lee", "role": "user"},
}


class ConnectionManager:
    """SSE 연결 상태 관리."""

    def __init__(self):
        self.connections: Dict[str, Dict] = {}  # session_id -> connection info
        self._cleanup_task: Optional[asyncio.Task] = None

    def register(self, session_id: str, user_id: str):
        """새 연결 등록."""
        self.connections[session_id] = {
            "user_id": user_id,
            "connected_at": time.time(),
            "last_activity": time.time(),
            "heartbeats": 0,
        }
        logger.info(f"Connection registered: {session_id} (user: {user_id})")

    def update_activity(self, session_id: str):
        """연결 활동 시간 업데이트."""
        if session_id in self.connections:
            self.connections[session_id]["last_activity"] = time.time()

    def heartbeat(self, session_id: str):
        """Heartbeat 카운트 증가."""
        if session_id in self.connections:
            self.connections[session_id]["heartbeats"] += 1
            self.connections[session_id]["last_activity"] = time.time()

    def unregister(self, session_id: str):
        """연결 해제."""
        if session_id in self.connections:
            info = self.connections.pop(session_id)
            duration = time.time() - info["connected_at"]
            logger.info(
                f"Connection closed: {session_id} "
                f"(user: {info['user_id']}, duration: {duration:.1f}s, "
                f"heartbeats: {info['heartbeats']})"
            )

    def get_stats(self) -> dict:
        """연결 통계."""
        return {
            "active_connections": len(self.connections),
            "connections": [
                {
                    "session_id": sid[:8] + "...",
                    "user_id": info["user_id"],
                    "connected_seconds": int(time.time() - info["connected_at"]),
                    "idle_seconds": int(time.time() - info["last_activity"]),
                    "heartbeats": info["heartbeats"],
                }
                for sid, info in self.connections.items()
            ]
        }

    async def cleanup_stale_connections(self):
        """유휴 연결 정리 (백그라운드 태스크)."""
        while True:
            try:
                await asyncio.sleep(60)  # 1분마다 체크
                now = time.time()
                stale = [
                    sid for sid, info in self.connections.items()
                    if now - info["last_activity"] > CONNECTION_TIMEOUT
                ]
                for sid in stale:
                    logger.warning(f"Cleaning up stale connection: {sid}")
                    self.unregister(sid)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    def start_cleanup(self):
        """정리 태스크 시작."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self.cleanup_stale_connections())

    def stop_cleanup(self):
        """정리 태스크 중지."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None


# 전역 연결 관리자
connection_manager = ConnectionManager()


def get_user_from_request(request: Request) -> str:
    """요청에서 사용자 ID 추출.

    우선순위:
    1. URL 파라미터: ?user=kim
    2. HTTP 헤더: X-User-ID: kim
    3. 기본값: system
    """
    # URL 파라미터
    user = request.query_params.get("user")
    if user and user in REGISTERED_USERS:
        return user

    # HTTP 헤더
    user = request.headers.get("X-User-ID")
    if user and user in REGISTERED_USERS:
        return user

    # 기본값
    return "system"


def get_user_from_scope(scope: dict) -> str:
    """ASGI scope에서 사용자 ID 추출."""
    # query string 파싱
    query_string = scope.get("query_string", b"").decode()
    if query_string:
        for param in query_string.split("&"):
            if param.startswith("user="):
                user = param.split("=", 1)[1]
                if user in REGISTERED_USERS:
                    return user

    # 헤더에서 추출
    headers = dict(scope.get("headers", []))
    user = headers.get(b"x-user-id", b"").decode()
    if user and user in REGISTERED_USERS:
        return user

    return "system"


def create_app():
    """Create Starlette app with SSE transport and multi-user support."""

    # 사용자별 서버 인스턴스 캐시
    user_servers: dict[str, MedicalKAGServer] = {}
    # MCP 서버 캐시
    mcp_servers: dict[str, any] = {}

    def get_server_for_user(user_id: str) -> MedicalKAGServer:
        """사용자별 서버 인스턴스 반환 (캐시 사용)."""
        if user_id not in user_servers:
            server = MedicalKAGServer(default_user=user_id)
            user_servers[user_id] = server
            logger.info(f"Created server instance for user: {user_id}")
        else:
            # 이미 생성된 서버의 사용자 컨텍스트 업데이트
            user_servers[user_id].set_user(user_id)
        return user_servers[user_id]

    def get_mcp_server_for_user(user_id: str):
        """사용자별 MCP 서버 인스턴스 반환 (캐시 사용)."""
        if user_id not in mcp_servers:
            kag_server = get_server_for_user(user_id)
            mcp_servers[user_id] = create_mcp_server(kag_server)
            logger.info(f"Created MCP server for user: {user_id}")
        return mcp_servers[user_id]

    # SSE transport 생성
    sse_transport = SseServerTransport("/messages")

    async def handle_sse(request: Request):
        """Handle SSE connection with user context and heartbeat."""
        import uuid
        session_id = str(uuid.uuid4())
        user_id = get_user_from_request(request)

        logger.info(f"SSE connection request: session={session_id[:8]}..., user={user_id}")

        # 연결 등록
        connection_manager.register(session_id, user_id)

        try:
            kag_server = get_server_for_user(user_id)
            mcp_server = get_mcp_server_for_user(user_id)

            async with sse_transport.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                # Heartbeat 태스크 시작
                heartbeat_task = asyncio.create_task(
                    send_heartbeat(session_id, streams[1])
                )

                try:
                    await mcp_server.run(
                        streams[0], streams[1], mcp_server.create_initialization_options()
                    )
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass

        except Exception as e:
            logger.error(f"SSE connection error: {session_id[:8]}... - {e}")
        finally:
            connection_manager.unregister(session_id)

        # SSE 연결은 스트림으로 처리되므로 빈 응답 반환
        return Response(status_code=200)

    async def send_heartbeat(session_id: str, write_stream):
        """주기적으로 heartbeat 전송."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                connection_manager.heartbeat(session_id)
                # MCP 프로토콜에서는 ping/pong이 없으므로 activity만 업데이트
                logger.debug(f"Heartbeat: {session_id[:8]}...")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

    async def health_check(request: Request):
        """Health check endpoint with connection stats."""
        user_id = get_user_from_request(request)
        kag_server = get_server_for_user(user_id)

        return JSONResponse({
            "status": "healthy",
            "server": "medical-kag",
            "version": "7.16.0",
            "current_user": user_id,
            "user_info": REGISTERED_USERS.get(user_id, {}),
            "neo4j_available": kag_server.neo4j_client is not None,
            "llm_enabled": getattr(kag_server, 'enable_llm', False),
            "active_users": list(user_servers.keys()),
            "connections": connection_manager.get_stats(),
            "settings": {
                "heartbeat_interval": HEARTBEAT_INTERVAL,
                "connection_timeout": CONNECTION_TIMEOUT,
            }
        })

    async def list_tools(request: Request):
        """List available tools."""
        from mcp.types import ListToolsRequest
        user_id = get_user_from_request(request)
        mcp_server = get_mcp_server_for_user(user_id)

        handler = mcp_server.request_handlers.get(ListToolsRequest)
        if handler:
            result = await handler(ListToolsRequest(method="tools/list"))
            inner = result.root if hasattr(result, 'root') else result
            tools = inner.tools if hasattr(inner, 'tools') else []
        else:
            tools = []
        return JSONResponse({
            "current_user": user_id,
            "tools": [{"name": t.name, "description": t.description} for t in tools]
        })

    async def list_users(request: Request):
        """등록된 사용자 목록."""
        return JSONResponse({
            "users": [
                {"id": uid, **info}
                for uid, info in REGISTERED_USERS.items()
            ],
            "active_sessions": list(user_servers.keys()),
            "connections": connection_manager.get_stats(),
        })

    async def add_user(request: Request):
        """새 사용자 등록 (관리자 전용)."""
        caller = get_user_from_request(request)
        if REGISTERED_USERS.get(caller, {}).get("role") != "admin":
            return JSONResponse(
                {"error": "Admin access required"},
                status_code=403
            )

        try:
            data = await request.json()
            user_id = data.get("id")
            name = data.get("name", user_id)
            role = data.get("role", "user")

            if not user_id:
                return JSONResponse({"error": "id required"}, status_code=400)

            if user_id in REGISTERED_USERS:
                return JSONResponse({"error": "User already exists"}, status_code=400)

            REGISTERED_USERS[user_id] = {"name": name, "role": role}
            logger.info(f"User registered: {user_id} by {caller}")

            return JSONResponse({
                "success": True,
                "user": {"id": user_id, "name": name, "role": role}
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    async def connection_stats(request: Request):
        """연결 상태 상세 조회."""
        return JSONResponse(connection_manager.get_stats())

    async def reset_server(request: Request):
        """서버 캐시 초기화 (재연결 지원).

        MCP 클라이언트가 disconnect된 후 재연결할 때 사용.
        - 모든 사용자 서버 인스턴스 초기화
        - MCP 서버 캐시 초기화
        - 기존 연결 정리

        Usage:
            curl -X POST http://localhost:8000/reset
            curl -X POST http://localhost:8000/reset?user=kim  # 특정 사용자만
        """
        user_id = request.query_params.get("user")

        try:
            if user_id:
                # 특정 사용자만 초기화
                if user_id in user_servers:
                    # Neo4j 연결 정리
                    server = user_servers[user_id]
                    if hasattr(server, 'neo4j_client') and server.neo4j_client:
                        try:
                            await server.neo4j_client.close()
                        except Exception:
                            pass
                    del user_servers[user_id]
                    logger.info(f"Reset server for user: {user_id}")

                if user_id in mcp_servers:
                    del mcp_servers[user_id]

                return JSONResponse({
                    "success": True,
                    "message": f"Server reset for user: {user_id}",
                    "active_users": list(user_servers.keys()),
                })
            else:
                # 모든 사용자 초기화
                reset_count = len(user_servers)

                # Neo4j 연결 정리
                for uid, server in user_servers.items():
                    if hasattr(server, 'neo4j_client') and server.neo4j_client:
                        try:
                            await server.neo4j_client.close()
                        except Exception:
                            pass

                user_servers.clear()
                mcp_servers.clear()

                # 연결 정보도 정리
                stale_sessions = list(connection_manager.connections.keys())
                for sid in stale_sessions:
                    connection_manager.unregister(sid)

                logger.info(f"Reset all servers ({reset_count} users)")

                return JSONResponse({
                    "success": True,
                    "message": f"All servers reset ({reset_count} users cleared)",
                    "cleared_connections": len(stale_sessions),
                })

        except Exception as e:
            logger.error(f"Reset error: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    async def restart_neo4j(request: Request):
        """Neo4j 연결 재설정.

        Neo4j 연결이 끊어졌을 때 재연결.

        Usage:
            curl -X POST http://localhost:8000/restart
        """
        try:
            reconnected = []
            failed = []

            for user_id, server in user_servers.items():
                try:
                    if hasattr(server, 'neo4j_client') and server.neo4j_client:
                        # 기존 연결 닫기
                        try:
                            await server.neo4j_client.close()
                        except Exception:
                            pass

                        # 새 연결 생성
                        await server.neo4j_client.connect()
                        reconnected.append(user_id)
                        logger.info(f"Neo4j reconnected for user: {user_id}")
                except Exception as e:
                    failed.append({"user": user_id, "error": str(e)})
                    logger.error(f"Neo4j reconnect failed for {user_id}: {e}")

            return JSONResponse({
                "success": len(failed) == 0,
                "reconnected": reconnected,
                "failed": failed,
            })

        except Exception as e:
            logger.error(f"Restart error: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    async def ping(request: Request):
        """간단한 ping 엔드포인트 (서버 생존 확인용)."""
        return JSONResponse({
            "pong": True,
            "timestamp": time.time(),
            "active_connections": len(connection_manager.connections),
        })

    # Lifespan 핸들러 (시작/종료 시 정리 태스크 관리)
    @asynccontextmanager
    async def lifespan(app):
        # 시작
        connection_manager.start_cleanup()
        logger.info("Connection cleanup task started")
        yield
        # 종료
        connection_manager.stop_cleanup()
        logger.info("Connection cleanup task stopped")

    # Routes - /messages는 Mount로 처리
    routes = [
        Route("/sse", endpoint=handle_sse),
        Mount("/messages", app=sse_transport.handle_post_message),
        Route("/health", endpoint=health_check),
        Route("/ping", endpoint=ping),
        Route("/tools", endpoint=list_tools),
        Route("/users", endpoint=list_users),
        Route("/users/add", endpoint=add_user, methods=["POST"]),
        Route("/connections", endpoint=connection_stats),
        Route("/reset", endpoint=reset_server, methods=["POST"]),
        Route("/restart", endpoint=restart_neo4j, methods=["POST"]),
    ]

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)


async def main():
    parser = argparse.ArgumentParser(description="Medical KAG MCP Server (SSE)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--heartbeat", type=int, default=30, help="Heartbeat interval (seconds)")
    parser.add_argument("--timeout", type=int, default=300, help="Connection timeout (seconds)")
    args = parser.parse_args()

    if not SSE_AVAILABLE:
        print(f"Error: SSE transport not available. Install dependencies:")
        print(f"  pip install 'mcp[sse]' starlette uvicorn")
        print(f"Import error: {IMPORT_ERROR}")
        sys.exit(1)

    # 설정 적용
    global HEARTBEAT_INTERVAL, CONNECTION_TIMEOUT
    HEARTBEAT_INTERVAL = args.heartbeat
    CONNECTION_TIMEOUT = args.timeout

    logger.info("=" * 60)
    logger.info("Medical KAG MCP Server (Multi-User SSE) v7.16.0")
    logger.info("=" * 60)
    logger.info(f"Server URL: http://{args.host}:{args.port}")
    logger.info(f"SSE endpoint: http://{args.host}:{args.port}/sse?user=<user_id>")
    logger.info(f"Health check: http://{args.host}:{args.port}/health")
    logger.info(f"Ping:         http://{args.host}:{args.port}/ping")
    logger.info(f"List tools:   http://{args.host}:{args.port}/tools")
    logger.info(f"List users:   http://{args.host}:{args.port}/users")
    logger.info(f"Connections:  http://{args.host}:{args.port}/connections")
    logger.info(f"Reset:        curl -X POST http://{args.host}:{args.port}/reset")
    logger.info(f"Restart Neo4j: curl -X POST http://{args.host}:{args.port}/restart")
    logger.info("-" * 60)
    logger.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
    logger.info(f"Connection timeout: {CONNECTION_TIMEOUT}s")
    logger.info("-" * 60)
    logger.info("Registered users:")
    for uid, info in REGISTERED_USERS.items():
        logger.info(f"  - {uid}: {info['name']} ({info['role']})")
    logger.info("=" * 60)

    app = create_app()

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        timeout_keep_alive=CONNECTION_TIMEOUT,  # Keep-alive 타임아웃
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
