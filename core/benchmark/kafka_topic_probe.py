import argparse
import json
import os
import time

from kafka import KafkaAdminClient, KafkaConsumer, TopicPartition


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Kafka topic throughput and lag")
    parser.add_argument("--bootstrap-servers", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    parser.add_argument("--topic", default=os.getenv("KAFKA_TOPIC", "netops.facts.raw.v1"))
    parser.add_argument("--group-id", default=os.getenv("KAFKA_GROUP_ID", "benchmark-probe-v1"))
    parser.add_argument("--duration-sec", type=int, default=int(os.getenv("PROBE_DURATION_SEC", "60")))
    parser.add_argument("--from-beginning", action="store_true")
    args = parser.parse_args()

    consumer = KafkaConsumer(
        args.topic,
        bootstrap_servers=[x.strip() for x in args.bootstrap_servers.split(",") if x.strip()],
        group_id=args.group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest" if args.from_beginning else "latest",
        value_deserializer=lambda b: b.decode("utf-8"),
    )

    admin = KafkaAdminClient(
        bootstrap_servers=[x.strip() for x in args.bootstrap_servers.split(",") if x.strip()],
        client_id="topic-probe",
    )

    start = time.time()
    count = 0
    byte_count = 0

    while time.time() - start < args.duration_sec:
        batch = consumer.poll(timeout_ms=1000, max_records=1000)
        for records in batch.values():
            for msg in records:
                count += 1
                byte_count += len(msg.value)

    elapsed = max(time.time() - start, 1e-6)
    eps = count / elapsed
    mbps = (byte_count / (1024 * 1024)) / elapsed

    partitions = [TopicPartition(args.topic, p.partition) for p in consumer.partitions_for_topic(args.topic) or []]
    end_offsets = consumer.end_offsets(partitions)
    consumer_offsets = {tp: consumer.position(tp) for tp in partitions}
    lag_total = sum(max(end_offsets[tp] - consumer_offsets[tp], 0) for tp in partitions)

    output = {
        "topic": args.topic,
        "group_id": args.group_id,
        "duration_sec": round(elapsed, 3),
        "messages_observed": count,
        "bytes_observed": byte_count,
        "events_per_sec": round(eps, 2),
        "mb_per_sec": round(mbps, 2),
        "partition_count": len(partitions),
        "lag_total": int(lag_total),
    }
    print(json.dumps(output, ensure_ascii=True))

    consumer.close()
    admin.close()


if __name__ == "__main__":
    main()
