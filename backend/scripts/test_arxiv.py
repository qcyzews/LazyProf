import arxiv
from typing import List
from pydantic import BaseModel

class ArticleMetadata(BaseModel):
    arxiv_id: str
    title: str
    authors: List[str]
    published: str
    summary: str
    pdf_url: str

def search_arxiv(query: str, max_results: int = 5) -> List[ArticleMetadata]:
    """Przeszukuje arXiv API i zwraca ustrukturyzowaną listę artykułów."""
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )

    results = []
    for result in client.results(search):
        # Wyciągamy ID bez pełnej ścieżki URL (np. '2303.18223v1' -> '2303.18223')
        paper_id = result.entry_id.split('/')[-1]
        
        article = ArticleMetadata(
            arxiv_id=paper_id,
            title=result.title.replace("\n", " "),
            authors=[author.name for author in result.authors],
            published=result.published.strftime("%Y-%m-%d"),
            summary=result.summary.replace("\n", " "),
            pdf_url=result.pdf_url
        )
        results.append(article)
    
    return results

if __name__ == "__main__":
    test_query = "Retrieval Augmented Generation for Large Language Models"
    print(f"🔎 Szukam na arXiv: '{test_query}'...\n")
    
    articles = search_arxiv(test_query, max_results=3)
    
    for i, art in enumerate(articles, 1):
        print(f"[{i}] {art.title}")
        print(f"    ID: {art.arxiv_id} | Data: {art.published}")
        print(f"    Autorzy: {', '.join(art.authors[:3])}...")
        print(f"    PDF: {art.pdf_url}")
        print(f"    Abstrakt: {art.summary[:150]}...\n")