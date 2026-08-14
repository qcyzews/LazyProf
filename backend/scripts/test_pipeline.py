import asyncio
import json
import sys
from httpx import AsyncClient
from httpx_sse import aconnect_sse

BASE_URL = "http://127.0.0.1:8000/api/v1"

async def test_full_pipeline():
    async with AsyncClient(timeout=120.0) as client:
        # --- STEP 1: Search arXiv ---
        query = "Retrieval Augmented Generation"
        print(f"🔍 1. Searching arXiv for: '{query}'...")
        
        search_response = await client.post(
            f"{BASE_URL}/search",
            json={"query": query, "max_results": 2}
        )
        
        if search_response.status_code != 200:
            print(f"❌ Search Error: {search_response.status_code} - {search_response.text}")
            return

        articles = search_response.json()
        print(f"✅ Found {len(articles)} paper(s):\n")
        
        selected_articles = []
        for art in articles:
            print(f"  • [{art['arxiv_id']}] {art['title']}")
            selected_articles.append({
                "title": art["title"],
                "arxiv_id": art["arxiv_id"],
                "pdf_url": art["pdf_url"]
            })

        print("\n" + "="*60 + "\n")

        # --- STEP 2: Analyze & Stream English Report ---
        user_instruction = "Compare the RAG architectures proposed in these papers, highlighting their key contributions and comparative benchmarks in a summary table."
        print(f"🚀 2. Launching analyze-stream with instruction:\n   \"{user_instruction}\"\n")
        print("--- SSE ANALYSIS STREAM ---")

        english_report = ""
        payload = {
            "articles": selected_articles,
            "user_instruction": user_instruction
        }

        async with aconnect_sse(client, "POST", f"{BASE_URL}/analyze-stream", json=payload) as event_source:
            async for event in event_source.aiter_sse():
                event_type = event.event
                try:
                    data = json.loads(event.data)
                except json.JSONDecodeError:
                    data = event.data

                if event_type == "status":
                    print(f"\n⚙️  [STATUS]: {data.get('message')}\n")
                elif event_type == "token":
                    content = data.get("content", "")
                    english_report += content
                    sys.stdout.write(content)
                    sys.stdout.flush()
                elif event_type == "complete":
                    print("\n\n✅ [COMPLETE]: English report generated successfully!")
                    break
                elif event_type == "error":
                    print(f"\n❌ [ERROR]: {data.get('message')} - {data.get('detail')}")
                    return

        print("\n" + "="*60 + "\n")

        # --- STEP 3: Translate Report to Polish ---
        print("🌐 3. Launching translate-stream (English -> Polish)...\n")
        print("--- SSE TRANSLATION STREAM ---")
        
        translate_payload = {
            "text": english_report,
            "target_language": "Polish"
        }

        async with aconnect_sse(client, "POST", f"{BASE_URL}/translate-stream", json=translate_payload) as event_source:
            async for event in event_source.aiter_sse():
                event_type = event.event
                try:
                    data = json.loads(event.data)
                except json.JSONDecodeError:
                    data = event.data

                if event_type == "status":
                    print(f"\n⚙️  [STATUS]: {data.get('message')}\n")
                elif event_type == "token":
                    content = data.get("content", "")
                    sys.stdout.write(content)
                    sys.stdout.flush()
                elif event_type == "complete":
                    print("\n\n✅ [COMPLETE]: Translation finished successfully!")
                    break
                elif event_type == "error":
                    print(f"\n❌ [ERROR]: {data.get('message')} - {data.get('detail')}")
                    break

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())