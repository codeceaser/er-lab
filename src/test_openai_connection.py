from openai import OpenAI

def main() -> None:
    openai = OpenAI()

    response = openai.responses.create(
        model="gpt-5-mini",
        input="Reply with exactly: API connection successful"
    )

    print(response.output_text)

if __name__ == "__main__":
    main()

