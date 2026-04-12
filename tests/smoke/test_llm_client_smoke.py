import asyncio
from dotenv import load_dotenv
load_dotenv()

from services.llm.client import OpenRouterClient

async def main():
    client = OpenRouterClient()
    messages = [{"role": "user", "content": "Hai! Ucapkan 'Tes sukses' dan tidak ada yang lain."}]
    print("Sending message...")
    try:
        response = await client.chat(messages)
        print("Response:", response)
    except Exception as e:
        print("Exception caught:", str(e))

if __name__ == "__main__":
    asyncio.run(main())
