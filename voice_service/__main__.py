import argparse
import sys

from voice_service import models, server


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m voice_service",
                                description="Local Hearing and Speaking for Jarvis.")
    p.add_argument("--port", type=int, default=8731)
    p.add_argument("--hearing", choices=sorted(models.HEARING), default="parakeet",
                   help="Hearing model (default: parakeet)")
    p.add_argument("--speaking", choices=sorted(models.SPEAKING), default="kokoro",
                   help="Speaking model (default: kokoro)")
    p.add_argument("--voice", default="bm_george", help="Kokoro Voice (default: bm_george)")
    p.add_argument("--fake-heard", default="fake hearing",
                   help="what the fake Hearing model hears")
    args = p.parse_args(argv)

    try:
        print(f"  voice-service · loading Hearing model {args.hearing}", flush=True)
        hearing = models.HEARING[args.hearing](args)
        print(f"  voice-service · loading Speaking model {args.speaking} ({args.voice})", flush=True)
        speaking = models.SPEAKING[args.speaking](args)
    except Exception as e:                                # noqa: BLE001
        print(f"  voice-service · cannot start: {e}", file=sys.stderr, flush=True)
        return 1
    srv = server.make_server(args.port, hearing, speaking, args.voice)
    print(f"  voice-service · ready on http://{server.HOST}:{args.port} "
          f"· device {hearing.device}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  voice-service · down.")
        srv.shutdown()


if __name__ == "__main__":
    sys.exit(main())
