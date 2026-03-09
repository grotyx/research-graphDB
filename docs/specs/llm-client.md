# LLM Client Specification

## Overview

통합 LLM 클라이언트 모듈로, Claude (Primary) 및 Gemini (Legacy) API를 지원합니다.

### 목적
- **통합 인터페이스**: 환경변수 기반 자동 선택
- Claude API 호출 (기본값: Haiku 4.5 + Sonnet 폴백)
- Gemini API 호출 (레거시 호환)
- Rate limiting 및 retry 처리
- JSON 구조화 출력 지원
- 응답 캐싱 및 비용 추적

### 입출력 요약
- **입력**: 프롬프트 텍스트, 시스템 프롬프트, JSON 스키마
- **출력**: 생성된 텍스트 또는 구조화된 JSON

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     llm/__init__.py                             │
├─────────────────────────────────────────────────────────────────┤
│  LLM_PROVIDER 환경변수 확인                                      │
│                                                                 │
│  if LLM_PROVIDER == "gemini":                                   │
│      LLMClient = GeminiClient   (레거시)                         │
│  else:                                                          │
│      LLMClient = ClaudeClient   (기본값)                         │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐      ┌─────────────────────┐          │
│  │   ClaudeClient      │      │   GeminiClient      │          │
│  │   (claude_client.py)│      │   (gemini_client.py)│          │
│  ├─────────────────────┤      ├─────────────────────┤          │
│  │ • Haiku 4.5 (기본)   │      │ • Gemini 2.5 Flash  │          │
│  │ • Sonnet 4.5 (폴백)  │      │ • JSON Schema 지원   │          │
│  │ • 8K→16K 자동 확장   │      │ • Rate Limiting     │          │
│  │ • Extended Thinking  │      │                     │          │
│  └─────────────────────┘      └─────────────────────┘          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Structures

### LLMConfig (Unified)

```python
# 환경변수에 따라 ClaudeConfig 또는 GeminiConfig로 매핑됨
from llm import LLMConfig

config = LLMConfig(
    temperature=0.1,
    max_output_tokens=8192
)
```

### ClaudeConfig

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ClaudeConfig:
    """Claude API 설정."""
    api_key: Optional[str] = None       # ANTHROPIC_API_KEY 환경변수
    model: str = "claude-haiku-4-5-20250514"  # Haiku 4.5 (기본)
    fallback_model: str = "claude-sonnet-4-5-20250514"  # Sonnet 4.5 (폴백)
    max_retries: int = 3
    timeout: float = 60.0               # 초
    temperature: float = 0.1
    max_output_tokens: int = 8192       # Haiku: 8K, Sonnet: 16K
    auto_fallback: bool = True          # 토큰 초과 시 자동 폴백
```

### GeminiConfig (Legacy)

```python
@dataclass
class GeminiConfig:
    """Gemini API 설정 (레거시)."""
    api_key: Optional[str] = None       # GEMINI_API_KEY 환경변수
    model: str = "gemini-2.5-flash-preview-05-20"
    max_retries: int = 3
    requests_per_minute: int = 2000
    tokens_per_minute: int = 4_000_000
    timeout: float = 30.0
    temperature: float = 0.1
    max_output_tokens: int = 8192
```

### LLMResponse (Unified)

```python
@dataclass
class LLMResponse:
    """LLM API 응답."""
    text: str                         # 생성된 텍스트
    input_tokens: int                 # 입력 토큰 수
    output_tokens: int                # 출력 토큰 수
    latency_ms: float                 # 응답 시간 (밀리초)
    model_used: str                   # 실제 사용된 모델
    cached: bool = False              # 캐시 히트 여부
    cost_usd: float = 0.0             # 예상 비용 (USD)
    fallback_used: bool = False       # 폴백 모델 사용 여부 (Claude only)
```

---

## Usage Examples

### 1. 기본 사용 (환경변수 기반)

```python
from llm import LLMClient, LLMConfig

# 환경변수 LLM_PROVIDER에 따라 Claude 또는 Gemini 사용
client = LLMClient(config=LLMConfig(temperature=0.3))

# 텍스트 생성
response = await client.generate("Explain TLIF surgery")
print(response.text)
print(f"Model used: {response.model_used}")
```

### 2. 명시적 Claude 사용

```python
from llm import ClaudeClient, ClaudeConfig

client = ClaudeClient(config=ClaudeConfig(
    model="claude-haiku-4-5-20250514",
    max_output_tokens=4096
))

response = await client.generate(
    prompt="Summarize this medical paper",
    system_prompt="You are a medical research assistant."
)
```

### 3. JSON 구조화 출력

```python
schema = {
    "type": "object",
    "properties": {
        "interventions": {
            "type": "array",
            "items": {"type": "string"}
        },
        "outcomes": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}

response = await client.generate_json(
    prompt="Extract interventions and outcomes from: ...",
    schema=schema
)
# response는 파싱된 dict
```

### 4. 하위 호환성 (gemini_client 파라미터)

```python
# 기존 코드와의 호환성 유지
class MyProcessor:
    def __init__(
        self,
        llm_client=None,
        gemini_client=None  # 레거시 파라미터
    ):
        client = llm_client or gemini_client
        self.llm = client
        self.gemini = self.llm  # 하위 호환성 속성
```

---

## Claude Model Specifications

### Claude Haiku 4.5 (Default)
- **Model ID**: `claude-haiku-4-5-20250514`
- **Max Output Tokens**: 8,192
- **Strengths**: 빠른 응답, 낮은 비용
- **Use Case**: 일반 텍스트 생성, 메타데이터 추출

### Claude Sonnet 4.5 (Fallback)
- **Model ID**: `claude-sonnet-4-5-20250514`
- **Max Output Tokens**: 16,384
- **Strengths**: 더 긴 출력, 복잡한 추론
- **Use Case**: 긴 문서 요약, 복잡한 분석

### Auto-Fallback Mechanism

```python
async def generate(self, prompt: str, ...) -> LLMResponse:
    try:
        # 1. Haiku로 시도
        response = await self._call_api(self.config.model, prompt)
        return response
    except TokenOverflowError:
        if self.config.auto_fallback:
            # 2. Sonnet으로 폴백
            response = await self._call_api(
                self.config.fallback_model,
                prompt,
                max_tokens=16384
            )
            response.fallback_used = True
            return response
        raise
```

---

## Environment Variables

```bash
# .env 파일

# LLM Provider 선택 (기본값: claude)
LLM_PROVIDER=claude

# Claude API (Primary)
ANTHROPIC_API_KEY=sk-ant-...

# Gemini API (Legacy, 선택적)
GEMINI_API_KEY=AIza...
```

---

## Migration from Gemini to Claude

### Before (Gemini-only)

```python
from llm.gemini_client import GeminiClient, GeminiConfig

client = GeminiClient(config=GeminiConfig())
response = await client.generate("...")
```

### After (Unified Interface)

```python
from llm import LLMClient, LLMConfig

# 환경변수에 따라 Claude 또는 Gemini 자동 선택
client = LLMClient(config=LLMConfig())
response = await client.generate("...")
```

### Backward Compatibility

모든 모듈은 다음 패턴으로 하위 호환성 유지:

```python
from typing import Union
from llm import LLMClient, ClaudeClient, GeminiClient

class AnyModule:
    def __init__(
        self,
        llm_client: Union[LLMClient, ClaudeClient, GeminiClient] = None,
        gemini_client: Union[LLMClient, ClaudeClient, GeminiClient] = None  # 레거시
    ):
        client = llm_client or gemini_client
        self.llm = client
        self.gemini = self.llm  # 하위 호환성 속성
```

---

## Cost Tracking

```python
from llm import CostTracker

tracker = CostTracker()

# 응답마다 비용 추적
response = await client.generate("...")
tracker.add(response)

# 세션 비용 확인
print(f"Total cost: ${tracker.total_cost:.4f}")
print(f"Total tokens: {tracker.total_tokens}")
```

### Pricing (2025)

| Model | Input (per 1M) | Output (per 1M) |
|-------|----------------|-----------------|
| Claude Haiku 4.5 | $0.80 | $4.00 |
| Claude Sonnet 4.5 | $3.00 | $15.00 |
| Gemini 2.5 Flash | $0.075 | $0.30 |

---

## Error Handling

```python
from llm import LLMClient
from llm.claude_client import (
    ClaudeAPIError,
    TokenOverflowError,
    RateLimitError
)

try:
    response = await client.generate(long_prompt)
except TokenOverflowError as e:
    # 토큰 초과 (auto_fallback=False일 때)
    logger.warning(f"Token overflow: {e}")
except RateLimitError as e:
    # Rate limit 초과
    await asyncio.sleep(e.retry_after)
except ClaudeAPIError as e:
    # 기타 API 에러
    logger.error(f"API error: {e}")
```

---

## Testing

```bash
# LLM 모듈 테스트
PYTHONPATH=./src python -m pytest tests/llm/

# Claude 클라이언트 테스트
PYTHONPATH=./src python -m pytest tests/llm/test_claude_client.py

# 통합 테스트
PYTHONPATH=./src python -m pytest tests/llm/test_integration.py
```

---

## Related Files

- `src/llm/__init__.py` - 통합 인터페이스
- `src/llm/claude_client.py` - Claude API 클라이언트
- `src/llm/gemini_client.py` - Gemini API 클라이언트 (레거시)
- `src/llm/cache.py` - 응답 캐싱
- `src/llm/prompts.py` - 시스템 프롬프트 및 스키마

---

## Version History

- **v3.2.0** (2025-12-14): Claude를 기본 LLM으로 전환, 통합 인터페이스 추가
- **v3.0.0** (2025-12-05): Gemini 2.5 Flash 기반 초기 구현
