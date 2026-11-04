"""Launch a visible research window without installing a global Houdini package."""
import argparse
from hlab.window import ensure
from hlab.storage import home
from hlab.afterglow import window_dir
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--houdini")
    p.add_argument("--home")
    p.add_argument("--shot", choices=["afterglow"])
    args = p.parse_args()
    if args.shot:
        folder = Path(args.home or home()) / "shots" / args.shot
        hip = folder / "Afterglow.hip"
        if not hip.is_file():
            p.error("Build the shot with afterglow_build.py first")
        print(ensure(window_dir(folder), args.houdini, hip), flush=True)
    else:
        print(ensure(args.home, args.houdini), flush=True)


if __name__ == "__main__":
    main()
