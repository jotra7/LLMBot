#!/bin/bash
cd /home/johnt/LLMBot1
source venv/bin/activate

# Start the main bot
python main.py &

# Start the Dramatiq workers
python run_workers.py &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?