"""Launch a visible research window without installing a global Houdini package."""
import argparse
from hlab.window import ensure


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--houdini")
    p.add_argument("--home")
    args = p.parse_args()
    print(ensure(args.home, args.houdini), flush=True)


if __name__ == "__main__":
    main()
