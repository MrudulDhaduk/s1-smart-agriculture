# Alert Service (Cloud Run function)

**Owner:** Person 2
**Role:** Detects dry soil and reports sensor or storage failures (serverless, event-driven).
**Talks to:** Pub/Sub `alerts`, Firestore `alerts`, and the GCS archive bucket.

The `handle_alert` CloudEvent function validates Pub/Sub JSON, creates a Firestore
document keyed by `alert_id`, and archives the original JSON under the UTC date in
`detected_at_ms` at `alerts/YYYY/MM/DD/<alert_id>.json`. Duplicate deliveries do not reset an existing
Firestore document; GCS creation uses a generation precondition so objects are never
overwritten. Invalid messages are logged and acknowledged, while cloud client failures
are allowed to raise so Pub/Sub can retry.

## Local development

Use Python 3.12. From this directory, install `requirements.txt` and the test-only
dependency `pytest`, then start the Functions Framework:

```sh
python3.12 -m pip install -r requirements.txt pytest
GOOGLE_CLOUD_PROJECT=local ARCHIVE_BUCKET=local-alert-archive \
  python3.12 -m functions_framework --target handle_alert --signature-type cloudevent
```

The endpoint is `http://localhost:8080/`. Tests mock Firestore and GCS and do not
require cloud credentials or create cloud resources:

```sh
python3.12 -m pytest -q
```

To send the checked-in example through the local CloudEvent handler, in another shell:

```sh
python3.12 -c 'import base64,json,urllib.request; d=open("../../contracts/pubsub/alert.example.json","rb").read(); e={"specversion":"1.0","id":"local-example-1","source":"//pubsub.googleapis.com/projects/local/topics/alerts","type":"google.cloud.pubsub.topic.v1.messagePublished","datacontenttype":"application/json","data":{"message":{"data":base64.b64encode(d).decode(),"messageId":"local-example-1","publishTime":"2026-11-13T00:00:00Z"},"subscription":"projects/local/subscriptions/alerts-local"}}; r=urllib.request.Request("http://localhost:8080/",data=json.dumps(e).encode(),headers={"Content-Type":"application/cloudevents+json"}); print(urllib.request.urlopen(r).status)'
```
