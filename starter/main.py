from client import FoundryClient
from config import settings


def main() -> None:
    client = FoundryClient()
    answer = client.query(settings.prompts.summary_system_prompt, settings.prompts.summary_user_prompt)
    print(answer)


if __name__ == '__main__':
    main()