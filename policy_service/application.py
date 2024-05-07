import sys
import flask



app = flask.Flask(__name__)



@app.route('/reset', methods=['POST'])
def route__reset():
    print("/reset")
    return flask.jsonify(success=True), 200



@app.route('/info/event', methods=['POST'])
def route__info__event():
    j = flask.request.get_json()
    print("/info/event: received info for event:", j['event'], "user_uuid:", j['user_uuid'], "tick:", j['tick'])
    return flask.jsonify(stored=True), 200



@app.route('/info/job/complete', methods=['POST'])
def route__info__job__complete():
    j = flask.request.get_json()
    print("/info/job/complete: received info for job from event:", j['event'], "user_uuid:", j['user_uuid'], "tick:", j['tick'])
    return flask.jsonify(stored=True), 200



@app.route('/info/job/late', methods=['POST'])
def route__info__job__late():
    j = flask.request.get_json()
    print("/info/job/late: received info for job from event:", j['event'], "user_uuid:", j['user_uuid'], "tick:", j['tick'])
    return flask.jsonify(stored=True), 200



@app.route('/info/system-status', methods=['POST'])
def route__info__system_status():
    j = flask.request.get_json()
    print("/info/system-status: received system status for tick:", j['tick'])
    print("Status:", j)
    return flask.jsonify(stored=True), 200



@app.route('/policy/autoscaling', methods=['POST'])
def route__policy__autoscaling():
    j = flask.request.get_json()
    print("/policy/autoscaling: vserver_count:", j['vserver_count'], "tick:", j['tick'])
    # Sample policy: increase vserver count by 1 on tick 0 and every 125 ticks
    vserver_count = j['vserver_count']
    if j['tick'] % 125 == 0:
        updated_vserver_count = vserver_count + 1
    else:
        updated_vserver_count = vserver_count
    return flask.jsonify(updated_vserver_count=updated_vserver_count), 200



@app.route('/policy/submit', methods=['POST'])
def route__policy__submit():
    j = flask.request.get_json()
    print("/policy/submit: received event:", j['event'], "user_uuid:", j['user_uuid'], "tick:", j['tick'])
    # Sample policy: accept all requests with priority 100
    return flask.jsonify(accept=True, priority=100), 200



if __name__ == '__main__':
    app.run(host='127.0.0.1', port=sys.argv[1])
