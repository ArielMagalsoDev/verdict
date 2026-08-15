from .run import run_evals


def main() -> None:
    result = run_evals()
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
