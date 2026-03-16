"""
src/mlops/pipeline_flow.py
Prefect flow: полный MVP-пайплайн от скрапинга до Qdrant.
"""
from prefect import flow, task, get_run_logger
from prefect.task_runners import SequentialTaskRunner
import subprocess
import pathlib
import os


@task(retries=2, retry_delay_seconds=30)
def scrape(book_keys: list[str], out_dir: str = "data/raw", force: bool = False):
    logger = get_run_logger()
    for key in book_keys:
        logger.info(f"Scraping {key}...")
        cmd = ["python", "src/scraper/scrape.py", "--book", key, "--out", out_dir]
        if force:
            cmd.append("--force")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Scrape failed for {key}: {result.stderr}")
        logger.info(result.stdout[-500:] if result.stdout else "OK")


@task
def parse(input_dirs: list[str], out_dir: str = "data/processed",
          use_llm: bool = True, llm_budget: int = 300):
    logger = get_run_logger()
    cmd = [
        "python", "src/parser/parse_pipeline.py",
        "--out", out_dir,
        "--llm-budget", str(llm_budget),
    ]
    if not use_llm:
        cmd.append("--no-llm")
    for d in input_dirs:
        cmd += ["--input", d]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Parse failed: {result.stderr}")
    logger.info(result.stdout[-500:] if result.stdout else "OK")


@task
def load_postgres(jsonl_files: list[str]):
    logger = get_run_logger()
    cmd = ["python", "src/graph/pg_loader.py"] + \
          [arg for f in jsonl_files for arg in ["--input", f]]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"PG load failed: {result.stderr}")
    logger.info(result.stdout[-500:] if result.stdout else "OK")


@task
def build_neo4j():
    logger = get_run_logger()
    result = subprocess.run(
        ["python", "src/graph/build_graph.py"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Neo4j build failed: {result.stderr}")
    logger.info("Neo4j graph built")


@task
def align():
    logger = get_run_logger()
    result = subprocess.run(
        ["python", "src/align/align_parallel.py"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alignment failed: {result.stderr}")
    logger.info("Alignment complete")


@task
def vectorize(collection: str = "hymns_multilingual"):
    logger = get_run_logger()
    result = subprocess.run(
        ["python", "src/vector/vectorize.py", "--collection", collection],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Vectorize failed: {result.stderr}")
    logger.info(f"Vectorization complete: {collection}")


@flow(
    name="hymnography-mvp-pipeline",
    task_runner=SequentialTaskRunner(),
    description="MVP pipeline: Октоих глас 8, ЦСЯ + греч.",
)
def mvp_pipeline(
    books: list[str] = ("oktoih_cu", "oktoih_grc"),
    use_llm: bool = True,
    llm_budget: int = 300,
    force_scrape: bool = False,
):
    logger = get_run_logger()
    logger.info(f"Starting MVP pipeline for books: {books}")

    # 1. Скрапинг
    scrape(list(books), force=force_scrape)

    # 2. Парсинг
    raw_dirs = [f"data/raw/{b}" for b in books]
    parse(raw_dirs, use_llm=use_llm, llm_budget=llm_budget)

    # 3. PostgreSQL
    jsonl_files = [f"data/processed/{b}.jsonl" for b in books]
    load_postgres(jsonl_files)

    # 4. Neo4j
    build_neo4j()

    # 5. Выравнивание
    align()

    # 6. Векторизация
    vectorize("hymns_cu")
    vectorize("hymns_grc")
    vectorize("hymns_multilingual")

    logger.info("MVP pipeline complete!")


if __name__ == "__main__":
    mvp_pipeline()
