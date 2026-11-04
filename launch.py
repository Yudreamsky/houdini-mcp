"""Launch a visible research window without installing a global Houdini package."""
import argparse
from hlab.window import ensure
from hlab.storage import home,sha
from hlab.sop_lab import hip_path
from hlab.afterglow import window_dir
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--houdini")
    p.add_argument("--home")
    scene=p.add_mutually_exclusive_group()
    scene.add_argument("--shot", choices=["afterglow","rain"])
    scene.add_argument("--hip",type=Path)
    args = p.parse_args()
    if args.hip or args.shot=="rain":
        hip=hip_path(str(args.hip.resolve()) if args.hip else str(Path(args.home)/"shots"/"rain"/"Rain.hip") if args.home else "rain")
        directory=Path(args.home or home())/"scene-windows"/sha(hip)[:16]
        print(ensure(directory,args.houdini,hip),flush=True)
    elif args.shot:
        folder = Path(args.home or home()) / "shots" / args.shot
        hip = folder / "Afterglow.hip"
        if not hip.is_file():
            p.error("Build the shot with afterglow_build.py first")
        print(ensure(window_dir(folder), args.houdini, hip), flush=True)
    else:
        print(ensure(args.home, args.houdini), flush=True)


if __name__ == "__main__":
    main()
