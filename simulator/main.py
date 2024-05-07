import sys
import uuid
import random
import collections
import queue

import requests



class Event(object):
    LOGIN = 'LOGIN'
    MAIN = 'MAIN'
    HISTORY = 'HISTORY'
    BEGIN = 'BEGIN'
    SUBMIT = 'SUBMIT'



def seeded_uuid(rand):
    return str(uuid.UUID('{:032x}'.format(rand.randint(0, 2**128-1))))



def event_generator(user_uuid, user_rand):
    event = {'event_uuid': seeded_uuid(user_rand), 'action': Event.LOGIN, 'params': {}}
    yield event
    event_rate = user_rand.randint(20, 45)
    create_event_timer = user_rand.randint(1, event_rate)
    prev_action = 'LOGIN'
    prev_begin = None
    while True:
        create_event_timer -= 1
        if create_event_timer > 0:
            yield None
        else:
            assert bool(prev_begin) == (prev_action == Event.BEGIN), "prev_action and prev_begin out of sync"
            if prev_action == Event.LOGIN:
                action = Event.MAIN
            elif prev_action in {Event.MAIN, Event.HISTORY}:
                action = user_rand.choice((
                    Event.MAIN,
                    Event.HISTORY,
                    Event.BEGIN,
                ))
            elif prev_action == Event.BEGIN:
                action = user_rand.choice((
                    Event.MAIN,
                    Event.SUBMIT,
                ))
            elif prev_action == Event.SUBMIT:
                action = Event.MAIN
            else:
                raise Exception(f"Unsupported prev_action {prev_action}")
            event = {
                'event_uuid': seeded_uuid(user_rand),
                'action': action,
                'params': {},
            }
            if prev_action == Event.BEGIN:
                assert prev_begin
                event['params']['prev_begin'] = prev_begin
                prev_begin = None
            if action == Event.BEGIN:
                assert prev_begin is None
                event['params']['ntasks'] = user_rand.choice((100, 200, 400))
                prev_begin = event
            yield event
            prev_action = action
            create_event_timer = user_rand.randint(10 if action == Event.BEGIN else 5, event_rate)



def run_simulator(seed, tick_count, policy_service_url):
    assert policy_service_url.startswith('http://')
    policy_service_url = policy_service_url.strip('/')

    policy_service_session = requests.Session()
    def policy_service_request(route, json=None, raise_for_status=True):
        route = route.strip('/')
        url = f"{policy_service_url}/{route}"
        kwargs = {}
        if json:
            kwargs = {'json': json}
        res = policy_service_session.post(url, **kwargs)
        if raise_for_status:
            res.raise_for_status()
        return res.json()

    global_rand = random.Random(seed)

    user_gen_rate = global_rand.randint(4, 50)
    create_user_timer = global_rand.randint(1, user_gen_rate)

    job_task_waiting_counts = {}
    job_late_ticks = {}
    job_tick_limit = 15
    task_queue = queue.PriorityQueue()

    users = {}

    events = {}

    vserver_seed = global_rand.randint(0, 2**128)
    vserver_rand = random.Random(vserver_seed)

    vserver_capacity = 4
    vservers_active = {}
    vservers_active_deque = collections.deque()
    vservers_removed = {}

    vserver_tick_billing_interval = 100
    vserver_interval_charge = 100
    total_charge = 0

    total_server_ticks = 0

    issued_req = set()
    accepted_req = set()
    rejected_req = set()
    completed_req = set()
    late_req = set()

    # Simulation start: reset policy service state
    policy_service_request('/reset')

    # Run simulation for `tick_count` cycles
    for tick in range(tick_count):
        pprefix = '[T:{}]'.format(tick)

        # 1. Create any new users
        create_user_timer -= 1
        assert create_user_timer >= 0
        while create_user_timer == 0:
            user_uuid = seeded_uuid(global_rand)
            user_seed = global_rand.randint(0, 2**128)
            user_rand = random.Random(user_seed)
            users[user_uuid] = {
                'rand': user_rand,
                'seed': user_seed,
                'generator': event_generator(user_uuid, user_rand),
            }
            print(pprefix, "Created user:", user_uuid)
            create_user_timer = global_rand.randint(0, user_gen_rate)

        # 2. For each user: generate events
        for user_uuid, user_data in sorted(users.items()):
            event = next(user_data['generator'])
            if event:
                event_uuid = event['event_uuid']
                assert event_uuid not in events
                events[event_uuid] = event
                event['create_tick'] = tick

                policy_service_request('/info/event', json={
                    'event': event,
                    'tick': tick,
                    'user_uuid': user_uuid,
                })

                if event['action'] == Event.SUBMIT:
                    issued_req.add(event['event_uuid'])
                    assert 'prev_begin' in event['params']
                    prev_begin = event['params']['prev_begin']
                    j = policy_service_request('/policy/submit', json={
                        'event': event,
                        'tick': tick,
                        'user_uuid': user_uuid,
                        'prev_begin': prev_begin
                    })
                    priority = j['priority']
                    accept = j['accept']
                    print(pprefix, f"/policy/submit: received policy response accept={accept} priority={priority if accept else 'n/a'}")
                    if accept:
                        event_uuid = event['event_uuid']
                        ntasks = prev_begin['params']['ntasks']
                        assert event_uuid not in job_task_waiting_counts
                        job_task_waiting_counts[event_uuid] = ntasks
                        job_late_ticks[event_uuid] = tick + job_tick_limit
                        for i in range(ntasks):
                            task = {'event': event, 'id': i, 'ntasks': ntasks}
                            task_queue.put(((priority, tick, user_uuid), id(task), task))
                        accepted_req.add(event['event_uuid'])
                        print(pprefix, f"Enqueued {ntasks} tasks")
                    else:
                        rejected_req.add(event['event_uuid'])

        # 3. Check autoscaling policy
        vserver_count = len(vservers_active)
        j = policy_service_request('/policy/autoscaling', json={
            'tick': tick,
            'vserver_count': vserver_count,
        })
        updated_vserver_count = j['updated_vserver_count']
        assert updated_vserver_count is not None and updated_vserver_count >= 0, f"Received invalid updated_vserver_count: {updated_vserver_count}"
        print(pprefix, f"/policy/autoscaling: received policy response updated_vserver_count={updated_vserver_count} (current vserver count: {vserver_count})")
        if vserver_count < updated_vserver_count:
            for i in range(updated_vserver_count - vserver_count):
                vserver_uuid = seeded_uuid(vserver_rand)
                assert vserver_uuid not in vservers_active
                assert vserver_uuid not in vservers_removed
                vserver_data = {
                    'vserver_uuid': vserver_uuid,
                    'tick_init': tick,
                    'tick_last_billed': tick,
                }
                vservers_active_deque.append(vserver_uuid)
                vservers_active[vserver_uuid] = vserver_data
                print(pprefix, f"Created vserver {vserver_uuid}")
                total_charge += vserver_interval_charge
                print(pprefix, f"Charged {vserver_interval_charge} for vserver {vserver_uuid}: total_charge={total_charge}")
        elif vserver_count > updated_vserver_count:
            for i in range(vserver_count - updated_vserver_count):
                vserver_uuid = vservers_active_deque.popleft() # do not catch, IndexError is fatal and should crash the program
                vservers_removed[vserver_uuid] = vservers_active[vserver_uuid]
                del vservers_active[vserver_uuid]
                print(pprefix, f"Removed vserver {vserver_uuid}")
        vserver_count = len(vservers_active)
        assert vserver_count == updated_vserver_count, f"Fatal: autoscaling failed, vserver_count={vserver_count} updated_vserver_count={updated_vserver_count}"
        total_server_ticks += vserver_count

        # 4. Handle any late jobs
        for event_uuid, late_tick in sorted(job_late_ticks.items()):
            event = events[event_uuid]
            # Jobs are on time if they complete before the late tick value.
            assert tick <= late_tick, f"late_tick {late_tick} not handled by tick {tick}"
            if tick == late_tick:
                print(pprefix, "Event late:", event_uuid)
                del job_late_ticks[event_uuid]
                assert event_uuid not in late_req
                late_req.add(event_uuid)
                policy_service_request('/info/job/late', json={
                    'event': event,
                    'tick': tick,
                    'user_uuid': user_uuid,
                })

        # 5. Progress submitted jobs
        vcluster_capacity = len(vservers_active) * vserver_capacity
        tick_completed_task_count = 0
        for available_slot in range(vcluster_capacity):
            try:
                (task_priority, task_tick, task_user_uuid), _, task = task_queue.get_nowait()
            except queue.Empty:
                break
            tick_completed_task_count += 1
            event = task['event']
            event_uuid = event['event_uuid']
            assert event_uuid in job_task_waiting_counts
            assert job_task_waiting_counts[event_uuid] >= 1
            nwaiting = job_task_waiting_counts[event_uuid] = job_task_waiting_counts[event_uuid] - 1
            if nwaiting == 0:
                del job_task_waiting_counts[event_uuid]
                if event_uuid in job_late_ticks:
                    # On time
                    del job_late_ticks[event_uuid]
                else:
                    # Late
                    pass
                print(pprefix, "Event complete:", event_uuid)
                policy_service_request('/info/job/complete', json={
                    'event': event,
                    'tick': tick,
                    'user_uuid': user_uuid,
                })
                assert event_uuid not in completed_req
                completed_req.add(event_uuid)
        print(pprefix, f"Tasks completed: {tick_completed_task_count} / Cluster capacity: {vcluster_capacity}")

        # 6. Assess additional vserver charges
        for vserver_uuid, vserver_data in sorted(vservers_active.items()):
            next_billing_tick = vserver_data['tick_last_billed'] + vserver_tick_billing_interval
            assert next_billing_tick >= tick, f"Failed to bill vserver {vserver_uuid} in time: next_billing_tick={next_billing_tick} tick={tick}"
            if next_billing_tick == tick:
                total_charge += vserver_interval_charge
                vserver_data['tick_last_billed'] = tick
                print(pprefix, f"Charged {vserver_interval_charge} for vserver {vserver_uuid}: total_charge={total_charge}")

        # 7. Send system status
        policy_service_request('/info/system-status', json={
            'vserver_count': vserver_count,
            'vserver_details': [vservers_active[vserver_uuid] for vserver_uuid in vservers_active_deque],
            'task_queue_size': task_queue.qsize(),
            'tick': tick,
        })


    print("")
    print("vservers active:", len(vservers_active))
    print("vservers removed:", len(vservers_removed))
    print("")

    print("Total charge:", total_charge)
    print("Mean charge/tick:", total_charge / tick_count)
    print("Mean vservers/tick:", total_server_ticks / tick_count)
    print("Mean charge/vserver-tick:", total_charge / total_server_ticks)
    print("")

    print("Request statistics:")
    print("Issued:", len(issued_req))
    print("Accepted:", len(accepted_req))
    print("Rejected:", len(rejected_req))
    print("Completed:", len(completed_req))
    print("Late:", len(late_req))



if __name__ == '__main__':
    seed = int(sys.argv[1])
    tick_count = int(sys.argv[2])
    policy_service_url = sys.argv[3]
    run_simulator(seed, tick_count, policy_service_url)

