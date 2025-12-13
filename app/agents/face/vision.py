from langchain_core.messages import HumanMessage

def build_human_message(text: str, thumb_urls: list[str]) -> HumanMessage:
    if not thumb_urls:
        return HumanMessage(content=text)
    
    content = [{"type": "text", "text": text}]
    for url in thumb_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
        
    return HumanMessage(content=content)
