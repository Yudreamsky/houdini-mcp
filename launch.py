"""Launch a visible research window without installing a global Houdini package."""
import argparse
from hlab.window import ensure, manage, registered
from hlab.storage import home, sha, uid
from hlab.sop_lab import hip_path
from hlab.afterglow import window_dir
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--houdini")
    p.add_argument("--home")
    p.add_argument("--new-window", action="store_true",
                   help="Use the target HIP's dedicated window instead of reusing a scene window")
    scene=p.add_mutually_exclusive_group()
    scene.add_argument("--shot", choices=["afterglow","rain"])
    scene.add_argument("--hip",type=Path)
    args = p.parse_args()
    if args.new_window and not args.hip:
        p.error("--new-window requires --hip")
    if args.hip or args.shot=="rain":
        hip=hip_path(str(args.hip.resolve()) if args.hip else str(Path(args.home)/"shots"/"rain"/"Rain.hip") if args.home else "rain")
        root=Path(args.home or home()).resolve()
        directory=root/"scene-windows"/sha(hip)[:16]
        if args.hip and not args.new_window:
            candidates = list(registered(root, scene_only=True))
            for _, item in candidates:
                info = manage(root, "state", item["id"])
                if Path(info["hip"]).resolve() == hip:
                    print(info, flush=True)
                    return
            if len(candidates) > 1:
                p.error("Multiple scene windows are open; choose one with window_session(open), or pass --new-window")
            if candidates:
                item = candidates[0][1]
            else:
                # Concurrent first launches share ensure()'s existing directory lock.
                item = ensure(root/"scene-windows"/"workbench", args.houdini, hip)
            info = manage(root, "open", item["id"], str(hip))
            if info["status"] == "unsaved_changes":
                p.error("The existing scene has unsaved changes: " + info["hip"])
            print(info, flush=True)
            return
        if args.new_window:
            directory=directory.with_name(directory.name+"-"+uid())
        elif args.shot == "rain":
            item=ensure(directory, args.houdini, hip)
            info=manage(root, "open", item["id"], str(hip))
            if info["status"] == "unsaved_changes":
                p.error("The rain window has unsaved changes: " + info["hip"])
            print(info, flush=True)
            return
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
