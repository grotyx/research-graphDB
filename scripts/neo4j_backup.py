"""Neo4j Backup & Recovery Script for Spine GraphRAG.

Docker 컨테이너 내 Neo4j 데이터를 백업/복구합니다.
Neo4j 5.26-community는 neo4j-admin dump을 지원하지 않으므로,
APOC export/import + Docker volume copy를 사용합니다.

ROADMAP #7.2

Usage:
    # Backup (APOC JSON export + volume tar)
    python3 scripts/neo4j_backup.py backup
    python3 scripts/neo4j_backup.py backup --output-dir /path/to/backups

    # List existing backups
    python3 scripts/neo4j_backup.py list
    python3 scripts/neo4j_backup.py list --output-dir /path/to/backups

    # Restore from backup
    python3 scripts/neo4j_backup.py restore --from-file data/backups/neo4j_backup_20260317_120000.tar.gz

    # Cleanup old backups (keep last N)
    python3 scripts/neo4j_backup.py cleanup --keep 3
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Defaults
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "data" / "backups"
CONTAINER_NAME = "spine_graphrag_neo4j"
NEO4J_DATABASE = "neo4j"
DOCKER_COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"

# Backup contents
#   1. APOC JSON export (nodes + relationships) — portable, human-readable
#   2. Docker volume tar (raw data dir) — fast full restore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cmd(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )


def container_running() -> bool:
    """Check if the Neo4j Docker container is running."""
    try:
        result = run_cmd(
            ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME],
            check=False,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


def docker_exec(cmd: str, *, timeout: int = 300) -> subprocess.CompletedProcess:
    """Execute a command inside the Neo4j container."""
    return run_cmd(
        ["docker", "exec", CONTAINER_NAME, "bash", "-c", cmd],
        timeout=timeout,
    )


def cypher_exec(query: str, *, timeout: int = 300) -> subprocess.CompletedProcess:
    """Execute a Cypher query via cypher-shell inside the container."""
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "")
    cmd = (
        f'cypher-shell -u neo4j -p "{neo4j_password}" '
        f'-d {NEO4J_DATABASE} "{query}"'
    )
    return docker_exec(cmd, timeout=timeout)


def ensure_backup_dir(backup_dir: Path) -> None:
    """Create backup directory if it doesn't exist."""
    backup_dir.mkdir(parents=True, exist_ok=True)


def format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def do_backup(output_dir: Path) -> None:
    """Create a full backup: APOC JSON export + Docker volume tar.

    Strategy:
      1. APOC export — Cypher-level export of all nodes and relationships
         to a JSON file inside the container, then docker cp to host.
      2. Volume tar — tar the Neo4j /data directory from the container
         for a byte-level backup (faster restore, includes indexes).

    Both are bundled into a single timestamped .tar.gz archive.
    """
    ensure_backup_dir(output_dir)

    if not container_running():
        logger.error("Neo4j container '%s' is not running. Start it first.", CONTAINER_NAME)
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"neo4j_backup_{timestamp}"
    staging_dir = output_dir / backup_name
    staging_dir.mkdir(parents=True, exist_ok=True)

    # --- Step 1: APOC JSON export -------------------------------------------
    logger.info("Step 1/3: APOC JSON export (all nodes + relationships)...")
    apoc_filename = "graph_export.json"
    container_export_path = f"/var/lib/neo4j/import/{apoc_filename}"

    try:
        # Remove stale export if present
        docker_exec(f"rm -f {container_export_path}", timeout=30)

        # Run APOC export
        export_query = (
            f"CALL apoc.export.json.all('{apoc_filename}', "
            f"{{useTypes: true, storeNodeIds: false}})"
        )
        result = cypher_exec(export_query, timeout=600)
        logger.info("APOC export completed.")

        # Copy from container to host
        host_export_path = staging_dir / apoc_filename
        run_cmd([
            "docker", "cp",
            f"{CONTAINER_NAME}:{container_export_path}",
            str(host_export_path),
        ])
        logger.info(
            "APOC export copied: %s (%s)",
            host_export_path.name,
            format_size(host_export_path.stat().st_size),
        )

        # Clean up inside container
        docker_exec(f"rm -f {container_export_path}", timeout=30)

    except subprocess.CalledProcessError as e:
        logger.warning(
            "APOC export failed (APOC might not be installed): %s", e.stderr or e
        )
        logger.warning("Continuing with volume backup only.")

    # --- Step 2: Docker volume tar ------------------------------------------
    logger.info("Step 2/3: Docker volume tar (/data directory)...")
    volume_tar_name = "data_volume.tar.gz"
    container_tar_path = f"/tmp/{volume_tar_name}"

    try:
        docker_exec(
            f"tar czf {container_tar_path} -C /data .",
            timeout=600,
        )
        host_tar_path = staging_dir / volume_tar_name
        run_cmd([
            "docker", "cp",
            f"{CONTAINER_NAME}:{container_tar_path}",
            str(host_tar_path),
        ])
        logger.info(
            "Volume tar copied: %s (%s)",
            host_tar_path.name,
            format_size(host_tar_path.stat().st_size),
        )

        # Clean up inside container
        docker_exec(f"rm -f {container_tar_path}", timeout=30)

    except subprocess.CalledProcessError as e:
        logger.error("Volume tar failed: %s", e.stderr or e)
        sys.exit(1)

    # --- Step 3: Save metadata & bundle -------------------------------------
    logger.info("Step 3/3: Saving metadata and creating archive...")
    metadata = {
        "timestamp": timestamp,
        "created_at": datetime.now().isoformat(),
        "container": CONTAINER_NAME,
        "database": NEO4J_DATABASE,
        "contents": [
            f for f in os.listdir(staging_dir) if not f.endswith(".json") or f != "metadata.json"
        ],
    }

    # Get node/relationship counts
    try:
        result = cypher_exec("MATCH (n) RETURN count(n) AS cnt;", timeout=30)
        node_count = result.stdout.strip().split("\n")[-1].strip()
        metadata["node_count"] = node_count

        result = cypher_exec("MATCH ()-[r]->() RETURN count(r) AS cnt;", timeout=30)
        rel_count = result.stdout.strip().split("\n")[-1].strip()
        metadata["relationship_count"] = rel_count
    except Exception:
        pass

    with open(staging_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Create final .tar.gz
    final_archive = output_dir / f"{backup_name}.tar.gz"
    run_cmd([
        "tar", "czf", str(final_archive),
        "-C", str(output_dir),
        backup_name,
    ])

    # Remove staging directory
    run_cmd(["rm", "-rf", str(staging_dir)])

    archive_size = final_archive.stat().st_size
    logger.info(
        "Backup complete: %s (%s)",
        final_archive,
        format_size(archive_size),
    )


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def do_restore(from_file: Path) -> None:
    """Restore Neo4j from a backup archive.

    Strategy:
      1. Prefer volume restore (data_volume.tar.gz) for speed + full fidelity.
      2. Fall back to APOC import (graph_export.json) if volume tar is missing.

    The Neo4j container is stopped before restore and restarted after.
    """
    if not from_file.exists():
        logger.error("Backup file not found: %s", from_file)
        sys.exit(1)

    # Extract archive to temp location
    staging_dir = from_file.parent / f"_restore_staging_{os.getpid()}"
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Extracting backup archive: %s", from_file)
        run_cmd(["tar", "xzf", str(from_file), "-C", str(staging_dir)])

        # Find the inner directory
        inner_dirs = [
            d for d in staging_dir.iterdir()
            if d.is_dir() and d.name.startswith("neo4j_backup_")
        ]
        if inner_dirs:
            content_dir = inner_dirs[0]
        else:
            content_dir = staging_dir

        volume_tar = content_dir / "data_volume.tar.gz"
        apoc_json = content_dir / "graph_export.json"

        # --- Volume restore (preferred) ------------------------------------
        if volume_tar.exists():
            logger.info("Restoring from Docker volume tar...")
            _restore_volume(volume_tar)
        elif apoc_json.exists():
            logger.info("Volume tar not found. Restoring from APOC JSON export...")
            _restore_apoc(apoc_json)
        else:
            logger.error(
                "No restorable data found in archive. "
                "Expected data_volume.tar.gz or graph_export.json."
            )
            sys.exit(1)

    finally:
        # Clean up staging
        run_cmd(["rm", "-rf", str(staging_dir)], check=False)


def _restore_volume(volume_tar: Path) -> None:
    """Restore Neo4j /data from a volume tar archive."""
    logger.info("Stopping Neo4j container...")
    run_cmd(
        ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "stop", "neo4j"],
        check=False,
    )
    time.sleep(3)

    # Use a temporary container to write to the volume
    logger.info("Restoring data volume...")
    container_tar_path = "/tmp/restore_data.tar.gz"

    # Start a temp container with the same volume
    run_cmd([
        "docker", "run", "--rm", "-d",
        "--name", "neo4j_restore_temp",
        "-v", "rag_research_neo4j_data:/data",
        "alpine", "sleep", "300",
    ])

    try:
        # Copy tar into temp container
        run_cmd([
            "docker", "cp",
            str(volume_tar),
            f"neo4j_restore_temp:{container_tar_path}",
        ])

        # Clear existing data and extract
        run_cmd([
            "docker", "exec", "neo4j_restore_temp",
            "sh", "-c",
            f"rm -rf /data/* && tar xzf {container_tar_path} -C /data",
        ], timeout=600)
        logger.info("Volume data restored.")

    finally:
        run_cmd(["docker", "stop", "neo4j_restore_temp"], check=False)

    # Restart Neo4j
    logger.info("Starting Neo4j container...")
    run_cmd(
        ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "start", "neo4j"],
    )

    _wait_for_neo4j()
    logger.info("Restore complete. Neo4j is running.")


def _restore_apoc(apoc_json: Path) -> None:
    """Restore Neo4j from an APOC JSON export file."""
    if not container_running():
        logger.info("Starting Neo4j container...")
        run_cmd(
            ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "start", "neo4j"],
        )
        _wait_for_neo4j()

    container_import_path = f"/var/lib/neo4j/import/graph_export.json"

    # Copy JSON into container
    run_cmd([
        "docker", "cp",
        str(apoc_json),
        f"{CONTAINER_NAME}:{container_import_path}",
    ])

    # Clear existing data
    logger.info("Clearing existing data...")
    cypher_exec("MATCH (n) DETACH DELETE n;", timeout=300)

    # Import
    logger.info("Importing APOC JSON (this may take a while)...")
    import_query = "CALL apoc.import.json('graph_export.json');"
    cypher_exec(import_query, timeout=1800)

    # Clean up
    docker_exec(f"rm -f {container_import_path}", timeout=30)

    # Verify
    result = cypher_exec("MATCH (n) RETURN count(n) AS cnt;", timeout=30)
    logger.info("APOC restore complete. Nodes: %s", result.stdout.strip().split("\n")[-1].strip())

    # Rebuild indexes
    logger.info(
        "NOTE: Run 'python scripts/init_neo4j.py' to rebuild indexes and constraints."
    )


def _wait_for_neo4j(max_wait: int = 120) -> None:
    """Wait for Neo4j to become healthy."""
    logger.info("Waiting for Neo4j to become ready (max %ds)...", max_wait)
    start = time.time()
    while time.time() - start < max_wait:
        try:
            result = run_cmd(
                [
                    "docker", "inspect", "-f",
                    "{{.State.Health.Status}}", CONTAINER_NAME,
                ],
                check=False,
            )
            status = result.stdout.strip()
            if status == "healthy":
                logger.info("Neo4j is healthy.")
                return
            logger.debug("Neo4j status: %s", status)
        except Exception:
            pass
        time.sleep(5)

    logger.warning(
        "Neo4j did not become healthy within %ds. "
        "Check container logs: docker logs %s",
        max_wait,
        CONTAINER_NAME,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def do_list(output_dir: Path) -> None:
    """List existing backup files in the backup directory."""
    if not output_dir.exists():
        logger.info("No backup directory found: %s", output_dir)
        return

    backups = sorted(output_dir.glob("neo4j_backup_*.tar.gz"))
    if not backups:
        logger.info("No backups found in %s", output_dir)
        return

    print(f"\n{'Backup File':<50} {'Size':>10} {'Date':>20}")
    print("-" * 82)
    for bk in backups:
        stat = bk.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{bk.name:<50} {format_size(stat.st_size):>10} {mtime:>20}")

    print(f"\nTotal: {len(backups)} backup(s) in {output_dir}")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def do_cleanup(output_dir: Path, keep: int) -> None:
    """Remove old backups, keeping the most recent N."""
    if not output_dir.exists():
        logger.info("No backup directory found: %s", output_dir)
        return

    backups = sorted(
        output_dir.glob("neo4j_backup_*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
    )

    if len(backups) <= keep:
        logger.info(
            "Found %d backup(s), keeping %d. Nothing to remove.",
            len(backups),
            keep,
        )
        return

    to_remove = backups[: len(backups) - keep]
    to_keep = backups[len(backups) - keep :]

    logger.info("Keeping %d most recent backup(s):", keep)
    for bk in to_keep:
        logger.info("  KEEP: %s", bk.name)

    for bk in to_remove:
        size = format_size(bk.stat().st_size)
        bk.unlink()
        logger.info("  REMOVED: %s (%s)", bk.name, size)

    logger.info(
        "Cleanup done: removed %d, kept %d.",
        len(to_remove),
        len(to_keep),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Neo4j Backup & Recovery for Spine GraphRAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/neo4j_backup.py backup
  python3 scripts/neo4j_backup.py backup --output-dir /mnt/backups
  python3 scripts/neo4j_backup.py list
  python3 scripts/neo4j_backup.py restore --from-file data/backups/neo4j_backup_20260317_120000.tar.gz
  python3 scripts/neo4j_backup.py cleanup --keep 3
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # backup
    p_backup = subparsers.add_parser("backup", help="Create a Neo4j backup")
    p_backup.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"Backup output directory (default: {DEFAULT_BACKUP_DIR})",
    )

    # list
    p_list = subparsers.add_parser("list", help="List existing backups")
    p_list.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"Backup directory (default: {DEFAULT_BACKUP_DIR})",
    )

    # restore
    p_restore = subparsers.add_parser("restore", help="Restore Neo4j from backup")
    p_restore.add_argument(
        "--from-file",
        type=Path,
        required=True,
        help="Path to backup .tar.gz archive",
    )

    # cleanup
    p_cleanup = subparsers.add_parser("cleanup", help="Remove old backups")
    p_cleanup.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"Backup directory (default: {DEFAULT_BACKUP_DIR})",
    )
    p_cleanup.add_argument(
        "--keep",
        type=int,
        default=5,
        help="Number of recent backups to keep (default: 5)",
    )

    args = parser.parse_args()

    if args.command == "backup":
        do_backup(args.output_dir)
    elif args.command == "list":
        do_list(args.output_dir)
    elif args.command == "restore":
        do_restore(args.from_file)
    elif args.command == "cleanup":
        do_cleanup(args.output_dir, args.keep)


if __name__ == "__main__":
    main()
