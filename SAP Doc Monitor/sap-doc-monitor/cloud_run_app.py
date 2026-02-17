"""
Cloud Run HTTP Wrapper for SAP Documentation Monitor
Provides an HTTP endpoint that triggers the monitoring script
"""
from flask import Flask, jsonify
import logging
import os
import traceback
from main import main as run_monitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def trigger_monitor():
    """HTTP endpoint that triggers the monitoring script"""
    logger.info("="*80)
    logger.info("Received HTTP trigger request")
    logger.info("="*80)
    
    try:
        # Run the monitoring script
        logger.info("Starting SAP Documentation Monitor...")
        run_monitor()
        
        logger.info("Monitoring completed successfully")
        return jsonify({
            'status': 'success',
            'message': 'SAP Documentation monitoring completed successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Error during monitoring: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port)
