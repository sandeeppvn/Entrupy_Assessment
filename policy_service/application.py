import sys
from asyncio import current_task
from os import system

import flask

app = flask.Flask(__name__)


job_metrics = {
    'completed_jobs': 0,
    'late_jobs': 0,
    'total_jobs': 0
}

server_metrics = {
    'vserver_count': 0,
    'task_queue_size': 0,
}


@app.route('/reset', methods=['POST'])
def route__reset():
    print("/reset")
    job_metrics['completed_jobs'] = 0
    job_metrics['late_jobs'] = 0
    job_metrics['total_jobs'] = 0

    job_metrics['vserver_count'] = 0
    job_metrics['task_queue_size'] = 0
    
    return flask.jsonify(success=True), 200



@app.route('/info/event', methods=['POST'])
def route__info__event():
    j = flask.request.get_json()
    print("/info/event: received info for event:", j['event'], "user_uuid:", j['user_uuid'], "tick:", j['tick'])
    job_metrics['total_jobs'] += 1
    return flask.jsonify(stored=True), 200



@app.route('/info/job/complete', methods=['POST'])
def route__info__job__complete():
    j = flask.request.get_json()
    print("/info/job/complete: received info for job from event:", j['event'], "user_uuid:", j['user_uuid'], "tick:", j['tick'])
    job_metrics['completed_jobs'] += 1
    return flask.jsonify(stored=True), 200



@app.route('/info/job/late', methods=['POST'])
def route__info__job__late():
    j = flask.request.get_json()
    print("/info/job/late: received info for job from event:", j['event'], "user_uuid:", j['user_uuid'], "tick:", j['tick'])
    job_metrics['late_jobs'] += 1
    return flask.jsonify(stored=True), 200



@app.route('/info/system-status', methods=['POST'])
def route__info__system_status():
    j = flask.request.get_json()
    print("/info/system-status: received system status for tick:", j['tick'])
    print("Status:", j)
    job_metrics['vserver_count'] = j['vserver_count']
    job_metrics['task_queue_size'] = j['task_queue_size']

    return flask.jsonify(stored=True), 200



@app.route('/policy/autoscaling', methods=['POST'])
def route__policy__autoscaling():
    j = flask.request.get_json()
    print("/policy/autoscaling: vserver_count:", j['vserver_count'], "tick:", j['tick'])
    
    active_vserver_count = j['vserver_count']

    # Get the current server metrics
    current_vsserver_count = server_metrics['vserver_count']
    current_task_queue_size = server_metrics['task_queue_size']

    # Get the current job metrics
    current_completed_jobs = job_metrics['completed_jobs']
    current_late_jobs = job_metrics['late_jobs']
    current_total_jobs = job_metrics['total_jobs']

    if current_total_jobs > 0:
        queue_to_total_jobs_ratio = current_task_queue_size / current_total_jobs
        late_to_total_jobs_ratio = current_late_jobs / current_total_jobs
    else:
        queue_to_total_jobs_ratio = 0
        late_to_total_jobs_ratio = 0

    # If atleast 80% of the jobs are in the queue, scale up
    scale_up_threshold = 0.8

    # If less than 10% of the jobs are in the queue, scale down
    scale_down_threshold = 0.1

    # If atleast 1% of the jobs are late, scale up
    scale_up_late_jobs_threshold = 0.01

    # If less than 1% of the jobs are late, scale down
    scale_down_late_jobs_threshold = 0.01

    # Determine if we need to scale up or down
    if queue_to_total_jobs_ratio > scale_up_threshold or late_to_total_jobs_ratio > scale_up_late_jobs_threshold:
        updated_vserver_count = min(active_vserver_count + int(active_vserver_count * 0.2 + 1), 45) 
    elif queue_to_total_jobs_ratio < scale_down_threshold and late_to_total_jobs_ratio < scale_down_late_jobs_threshold:
        updated_vserver_count = max(active_vserver_count - int(active_vserver_count * 0.2 + 1), 1) # Ensure we have atleast 1 server
    else:
        updated_vserver_count = active_vserver_count

    print("Updated vserver count:", updated_vserver_count)
    return flask.jsonify(updated_vserver_count=updated_vserver_count), 200



@app.route('/policy/submit', methods=['POST'])
def route__policy__submit():
    j = flask.request.get_json()
    print("/policy/submit: received event:", j['event'], "user_uuid:", j['user_uuid'], "tick:", j['tick'])
    # Sample policy: accept all requests with priority 100
    return flask.jsonify(accept=True, priority=100), 200



if __name__ == '__main__':
    # app.run(host='127.0.0.1', port=sys.argv[1])
    # Run in debug mode
    app.run(host='127.0.0.1', port=sys.argv[1], debug=True)
