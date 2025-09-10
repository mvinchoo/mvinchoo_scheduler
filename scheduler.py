import time

from actions import SchedulerActions
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

log = logging.getLogger("mvinchoo-scheduler")


def main():
    while True:
        sa = SchedulerActions()
        sa.start_session()
        # Break for 2 seconds then start new session
        time.sleep(5)


if __name__ == "__main__":
    main()
