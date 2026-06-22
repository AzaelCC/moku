import asyncio

from pyinstrument import Profiler

from moku_backend.config import Settings
from moku_backend.db.engine import create_engine, create_sessionmaker
from moku_backend.services.recommendation_service import RecommendationService


async def main():
    settings = Settings()
    settings.database_url = (
        "postgresql+asyncpg://moku:moku@localhost:5434/moku"
    )

    engine = create_engine(settings)
    Session = create_sessionmaker(engine)

    profiler = Profiler(async_mode="enabled")

    async with Session() as session:
        recommendation_service = RecommendationService(session, settings)

        profiler.start()

        result = await recommendation_service.recommend(
            corpus_name="opensubtitles2024-zh_CN",
            top_k=50,
            candidate_count=100,
            horizon_days=365,
            top_k_allowed_words=8000,
        )

        profiler.stop()

    profiler.print()

    # Optional
    # profiler.write_html("recommend_profile.html")

    return result


if __name__ == "__main__":
    asyncio.run(main())