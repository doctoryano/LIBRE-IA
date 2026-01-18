#!/usr/bin/env python3
import argparse
DEFAULT_POWER_W = {"rtx3090":350,"rtx4090":450,"a100":300}
DEFAULT_EMISSION = 0.4
def estimate(gpu_type, gpus, hours, emission):
    p = DEFAULT_POWER_W.get(gpu_type, 300)
    kwh = p * gpus * hours / 1000.0
    kg = kwh * emission
    return kwh, kg
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--gpu_type", required=True)
    ap.add_argument("--gpus", type=int, default=1)
    ap.add_argument("--hours", type=float, required=True)
    ap.add_argument("--emission", type=float, default=DEFAULT_EMISSION)
    args=ap.parse_args()
    kwh, kg = estimate(args.gpu_type, args.gpus, args.hours, args.emission)
    print(f"Estimated kWh: {kwh:.2f}, kgCO2e: {kg:.2f}")
if __name__=="__main__": main()