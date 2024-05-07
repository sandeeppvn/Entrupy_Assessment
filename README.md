# Entrupy_Assessment


## Simulator

### Event generator
- Pace of events: 20-45
- create_event_timer: Delay before next event is generated
- Next action based on prev_action:
    - 'LOGIN': 'MAIN'
    - 'MAIN', 'HISTORY': 'MAIN', 'HISTORY', 'BEGIN'
    - 'BEGIN': 'MAIN', 'SUBMIT'
    - 'SUBMIT': 'MAIN'
- Adjust prev_begin to state and set to null for next action
- If action is BEGIN, set ntasks (100,200,400) and prev_begin as the current event
- Change prev_action to current action
- The time of the event is (10, event_rate) if action is not BEGIN, else it is (5, event_rate)

### Run Simulator
Coordinates user activity, task submission and autoscaling policies over a simulated period of time.
helper function: policy_service_request - From a json and route, makes a request to the policy service and returns the response while tracking the status.

- Generate random values
    - global_rand : Seed
    - user_gen_rate: Interval in which users are created (4,50)
    - job_task_waiting_counts: How many submitted tasks are waiting to be processed
    - job_late_ticks: Job uuid to tick count by which job should be completed
    - job_tick_limit: Max number of ticks allowed for a job to be completed. Marked late if beyond this limit.
    -  task_queue: Priority queue for tasks to be processed first

- users: uuid, users random generator, event generator
- events: uuid, event details and metadata

- Virtual Servers
    - capacity: Number of tasks it can handle simultaneously, 4
    - active: dictionary to track currently active vservers. key is server identifier
    - active_deque: Dequeue maintaining order of active servers 
    - removed: Removed vservers

- Billing and Cost Management
    - tick_billing_interval: How oftern (intervals) a server is billed in, 100 ticks
    - interval_charge: Cost at each billing interval, 100 (100 units per 100 ticks)
    - total_charge: Running total of charges
    - total_server_ticks: Total ticks for all servers. To cacluate average usage of vservers.

- Request sets
    - issued_req: All submitted jobs
    - accepted_req: Requests accepted by the policy service
    - rejected_req: Requests rejected by the policy service 
    - completed_req: Requests completed by the policy service
    - late_req: Requests that were late, completed after the deadline

#### 1. Create any new users
- Create a new user every user_gen_rate interval with a uuid and event
- create_user_timer is changed to stagger user creation

#### 2. Generate events for each user
- Iterate over each user and get the next event from the event generator
- Store the event with the tick at which it was generated
- Inform the policy service of the event
- If event action is SUBMIT, add the event to issued_req and send it to policy to check if it can be accepted and obatin its priority
- If accepted, 
    - get the number of tasks for the event and update job_task_waiting_counts
    - Calculate the deadline for the job : tick + job_tick_limit and update it to job_late_ticks
    - For each task, add it to the task_queue based on the priority
    - Add the event to accepted_req
- If rejected, add the event to rejected_req

#### 3. Check Autoscale Policy
- Get number of active servers and call the autoscaling endpoint
- Update the active servers based on the response
    - If more, add new servers, 
    - If less, remove servers by popleft from active_deque and add to removed
    - update vservers_active and vservers_active_deque, Update vservers internal charge on the total charge
- Update total_server_ticks based on the number of active servers

#### 4. Handling Late jobs
- Check if any job is late by comparing the current tick with the deadline
- If late, add it to late_req and remove the tasks from the task_queue and inform the policy service

#### 5. Process submitted tasks
- Calculate cluster capacity based on the number of active servers * capacity
- tick_completed_task_count: Tracks the number of tasks completed in the current tick
- Jobs are processed in the order of priority until the cluster capacity is reached or no more tasks are available
    - Update tick_completed_task_count
    - Get the event details and uuid from the task. Using job_task_waiting_counts, get the number of tasks for the job and decrease by 1.
    - Only ff all tasks are completed, 
        - add the job to completed_req, 
        - remove the event from job_task_waiting_counts. 
        - Add to late jobs if it is late.
        - Call job/complete endpoint of the policy with event, tick and user uuid
        - Add the job to completed_req


#### 6. Additional Billing
- For each active server, calculate the next billing interval : vserver_data['tick_last_billed'] + vserver_tick_billing_interval
- If the current tick is equal to the next billing interval, bill the server and update the total_charge with vserver_interval_charge and update the tick_last_billed to current tick.

#### 7. Send System Status
- Send a summary of the current system status to the policy service (active servers, active tasks queue size and current tick).


## Policy Service Application

### reset
- Reset the state of the policy before starting a new simulation

### info
- event: Recieves information about the event: event, user uuid, tick
- job/complete: Recieved information about the completed job: event, user uuid, tick
- job/late: Recieved information about the late job: event, user uuid, tick
- system-status: Recieved information about the system status: active servers, active tasks queue size and current tick

### policy
- autoscaling: Recieves the current number of active servers and tick and returns the updated number of active servers based on the autoscaling policy.
- submit: 
    - Extracts event data: event, uuid, tick from the json.  
    - Prioritize jobs and send back accepted or not.


## Improvements on the Autoscaling Policy
- Data Collection:
    - Collect more data on the system performance, user activity, and task completion times to make more informed decisions.
- Scaling Logic:
    - Implement more sophisticated scaling logic that takes into account the other collected data.
    - (Advanced) Use historical data to predict future trends and adjust the autoscaling policy accordingly.

## Improve Job Submission Handling
- Prioritize jobs based on the number of tasks, deadline and system load.
- Implement a reject logic for jobs that cannot be accepted due to system constraints while ensuring no more than 5% of jobs are rejected.
- (Advanced) Perform Batch Processing of jobs to optimize the system load. Aggregate similar jobs and process them together.

## TRIALS
### Base Trial
vservers active: 4
vservers removed: 0

Total charge: 1400
Mean charge/tick: 2.8
Mean vservers/tick: 2.5
Mean charge/vserver-tick: 1.12

Request statistics:
Issued: 97
Accepted: 97
Rejected: 0
Completed: 23
Late: 96

### Trial 1
scale_up_threshold = 0.2
scale_down_threshold = 0.05
scale_up_late_jobs_threshold = 0.02
scale_down_late_jobs_threshold = 0.01

vservers active: 100
vservers removed: 99

Total charge: 41400
Mean charge/tick: 82.8
Mean vservers/tick: 66.15
Mean charge/vserver-tick: 1.251700680272109

Request statistics:
Issued: 97
Accepted: 97
Rejected: 0
Completed: 97
Late: 18