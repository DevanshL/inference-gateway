#!/usr/bin/env python3
"""
HPA Load Test — hammers the gateway to trigger autoscaling.

Run this while watching:
  watch kubectl get hpa -n inference-gateway
  watch kubectl get pods -n inference-gateway

You should see pods scale from 1 → 2 → 3 within ~60-90 seconds.
"""
import asyncio
import httpx
import time
import sys

GATEWAY_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
CONCURRENCY = int(sys.argv[2]) if len(sys.argv) > 2 else 10
DURATION_S  = int(sys.argv[3]) if len(sys.argv) > 3 else 120

PROMPTS = [
    {"messages": [{"role": "user", "content": "What is 2+2?"}]},
    {"messages": [{"role": "user", "content": "Name 3 planets"}]},
    {"messages": [{"role": "user", "content": "What is Python?"}]},
    {"messages": [{"role": "user", "content": "Explain recursion briefly"}], "task_type": "reasoning"},
    {"messages": [{"role": "user", "content": "Write a hello world function"}], "task_type": "code"},
]

success = 0
errors  = 0
start   = time.time()

async def fire_request(client: httpx.AsyncClient, i: int):
    global success, errors
    payload = PROMPTS[i % len(PROMPTS)]
    try:
        resp = await client.post(f"{GATEWAY_URL}/infer", json=payload, timeout=60)
        if resp.status_code == 200:
            success += 1
        else:
            errors += 1
    except Exception:
        errors += 1

async def worker(worker_id: int):
    async with httpx.AsyncClient() as client:
        i = 0
        while time.time() - start < DURATION_S:
            await fire_request(client, worker_id + i)
            i += 1
            await asyncio.sleep(0.1)

async def main():
    print(f"\n🔥 HPA Load Test")
    print(f"   Target:      {GATEWAY_URL}")
    print(f"   Concurrency: {CONCURRENCY} workers")
    print(f"   Duration:    {DURATION_S}s")
    print(f"\n   Watch pods:  kubectl get pods -n inference-gateway -w")
    print(f"   Watch HPA:   kubectl get hpa -n inference-gateway\n")

    tasks = [worker(i) for i in range(CONCURRENCY)]

    # Progress reporter
    async def report():
        while time.time() - start < DURATION_S:
            elapsed = time.time() - start
            rps = (success + errors) / max(elapsed, 1)
            print(f"   [{elapsed:5.0f}s] success={success} errors={errors} rps={rps:.1f}")
            await asyncio.sleep(10)

    await asyncio.gather(*tasks, report())

    elapsed = time.time() - start
    total   = success + errors
    print(f"\n{'='*50}")
    print(f"  Done. {total} requests in {elapsed:.0f}s")
    print(f"  Success: {success} ({100*success//max(total,1)}%)")
    print(f"  Errors:  {errors}")
    print(f"  RPS:     {total/elapsed:.1f}")
    print(f"{'='*50}\n")

asyncio.run(main())