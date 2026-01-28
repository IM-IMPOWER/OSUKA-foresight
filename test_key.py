
import google.generativeai as genai


def main() -> None:
    # TODO: Replace with your actual API key.
    api_key = "AIzaSyAypzN6z_7dtMbFPrG4oHRmdJm5XtyFwv4"

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content("Say 'OK' if you can read this.")

    print("Request succeeded.")
    print("Response:")
    print(response.text)


if __name__ == "__main__":
    main()
