import argparse
import json
import os
import random
import string
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from kafka import KafkaProducer


def _payload(payload_bytes: int, seq: int) -> str:
    overhead = 120
    filler_len = max(payload_bytes - overhead, 16)
    filler = "".join(random.choices(string.ascii_letters + string.digits, k=filler_len))
    event = {
        "schema_version": 1,
        "event_id": f"bench-{seq}",
        "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "type": "benchmark",
        "subtype": "load",
        "action": "allow",
        "payload": filler,
    }
    return json.dumps(event, separators=(",", ":"), ensure_ascii=True)


def _build_producer(bootstrap_servers: str) -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=[x.strip() for x in bootstrap_servers.split(",") if x.strip()],
        acks="all",
        retries=10,
        linger_ms=20,
        compression_type="gzip",
        value_serializer=lambda x: x.encode("utf-8"),
    )


def _send_batch(
    producer: KafkaProducer,
    topic: str,
    start_seq: int,
    batch_size: int,
    payload_bytes: int,
) -> tuple[int, int]:
    total_bytes = 0
    futures = []

    for idx in range(batch_size):
        seq = start_seq + idx
        body = _payload(payload_bytes, seq)
        total_bytes += len(body)
        futures.append(producer.send(topic, key=f"bench-{seq}".encode("utf-8"), value=body))

    for future in futures:
        future.get(timeout=30)

    return batch_size, total_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description="Kafka load producer for NetOps phase-2 benchmark")
    parser.add_argument("--bootstrap-servers", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    parser.add_argument("--topic", default=os.getenv("KAFKA_TOPIC", "netops.facts.raw.v1"))
    parser.add_argument("--messages", type=int, default=int(os.getenv("BENCH_MESSAGES", "100000")))
    parser.add_argument("--payload-bytes", type=int, default=int(os.getenv("BENCH_PAYLOAD_BYTES", "1024")))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("BENCH_BATCH_SIZE", "1000")))
    parser.add_argument("--workers", type=int, default=int(os.getenv("BENCH_WORKERS", "2")))
    args = parser.parse_args()

    producer = _build_producer(args.bootstrap_servers)
    jobs = []
    seq = 0

    while seq < args.messages:
        n = min(args.batch_size, args.messages - seq)
        jobs.append((seq, n))
        seq += n

    sent = 0
    sent_bytes = 0
    started = time.time()

    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
        futures = [
            pool.submit(_send_batch, producer, args.topic, start_seq, batch, args.payload_bytes)
            for start_seq, batch in jobs
        ]
        for future in as_completed(futures):
            count, num_bytes = future.result()
            sent += count
            sent_bytes += num_bytes

    producer.flush()
    elapsed = max(time.time() - started, 1e-6)
    eps = sent / elapsed
    mbps = (sent_bytes / (1024 * 1024)) / elapsed

    print(
        json.dumps(
            {
                "bootstrap_servers": args.bootstrap_servers,
                "topic": args.topic,
                "messages": sent,
                "bytes": sent_bytes,
                "elapsed_sec": round(elapsed, 3),
                "events_per_sec": round(eps, 2),
                "mb_per_sec": round(mbps, 2),
                "workers": args.workers,
                "batch_size": args.batch_size,
                "payload_bytes": args.payload_bytes,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
