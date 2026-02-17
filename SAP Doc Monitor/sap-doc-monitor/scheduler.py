"""
SAP Documentation Monitor - Scheduled Runner
Runs the monitoring script at specified intervals using APScheduler
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging
import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the main monitoring function
from main import main as run_monitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def scheduled_job():
    """Execute the monitoring job"""
    logger.info("="*80)
    logger.info(f"Starting scheduled monitoring job at {datetime.now()}")
    logger.info("="*80)
    
    try:
        run_monitor()
        logger.info("Monitoring job completed successfully")
    except Exception as e:
        logger.error(f"Error during monitoring job: {str(e)}", exc_info=True)
    
    logger.info("="*80)
    logger.info(f"Scheduled job finished at {datetime.now()}")
    logger.info("="*80)


def main():
    """Set up and start the scheduler"""
    scheduler = BlockingScheduler()
    
    # ==========================================================================
    # SCHEDULE CONFIGURATION
    # ==========================================================================
    # Modify the cron expression below to set your desired schedule
    
    # Option 1: Run every 6 hours
    # scheduler.add_job(scheduled_job, 'interval', hours=6)
    
    # Option 2: Run daily at 9 AM
    # scheduler.add_job(scheduled_job, CronTrigger(hour=9, minute=0))
    
    # Option 3: Run twice daily (9 AM and 6 PM)
    # scheduler.add_job(scheduled_job, CronTrigger(hour='9,18', minute=0))
    
    # Option 4: Run every Monday at 8 AM
    # scheduler.add_job(scheduled_job, CronTrigger(day_of_week='mon', hour=8, minute=0))
    
    # Option 5: Run every hour (default)
    scheduler.add_job(scheduled_job, 'interval', hours=1)
    
    # ==========================================================================
    
    logger.info("SAP Documentation Monitor Scheduler Started")
    logger.info("Current schedule: Running every 1 hour")
    logger.info("Press Ctrl+C to exit")
    
    try:
        # Run once immediately on startup
        logger.info("Running initial check...")
        scheduled_job()
        
        # Then start the scheduler
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
