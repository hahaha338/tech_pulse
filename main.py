from fetchers.external_fetcher import fetch_external_trends
from notifier import send_notification
from summarizer import summarize
from utils.config import load_config
from utils.formatter import build_report, save_report
from utils.logger import setup_logger


def run() -> None:
    logger = setup_logger()
    logger.info("TechPulse job started")

    config = load_config()

    logger.info("Fetching external imaging trends")
    external_data = fetch_external_trends(config)

    logger.info("Generating summary")
    summary_body = summarize(
        external_data=external_data,
        config=config,
        logger=logger,
    )

    report = build_report(summary_body)
    report_path = save_report(report, config)
    logger.info("Report saved to %s", report_path)

    send_notification(report, config, logger=logger)

    logger.info("TechPulse job completed")


if __name__ == "__main__":
    run()