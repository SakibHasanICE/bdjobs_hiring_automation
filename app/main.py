# app/main.py
import asyncio

from models.sample_data import build_sample_job_posting
from services.job_posting_service import JobPostingService


async def main() -> None:
    job = build_sample_job_posting()
    service = JobPostingService()
    await service.post_job(job)


if __name__ == "__main__":
    asyncio.run(main())