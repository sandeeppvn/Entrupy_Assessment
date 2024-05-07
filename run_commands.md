Start your autoscaling policy service with:

``
python policy_service/application.py 5555
```

Run the simulation of users requesting jobs with:

```
python simulator/main.py [seed] [ticks] http://localhost:5555
```

For example,

```
python simulator/main.py 42 200 http://localhost:5555
```
