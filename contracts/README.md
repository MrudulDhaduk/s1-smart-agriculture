# contracts/ (shared, all 3 people)

The agreements between services. Build against these, and change them only if all 3 people agree.

- `*.proto`: gRPC service definitions (Partition Manager, Sensor Store)
- `kafka/`: JSON schemas for the `readings` and `results` topics
- `rest/`: REST endpoint specs for the public APIs
