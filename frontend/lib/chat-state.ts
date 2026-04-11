import type { AssistantPacket, CitationPacket, SourceDocument, WorkspaceMessage } from "@/lib/types";

function dedupeDocuments(documents: SourceDocument[]): SourceDocument[] {
  const seen = new Map<string, SourceDocument>();
  for (const document of documents) {
    seen.set(document.document_id, document);
  }
  return Array.from(seen.values());
}

function dedupeCitations(citations: CitationPacket[]): CitationPacket[] {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    const key = `${citation.citation_number}:${citation.document_id}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function applyPacketToMessage(
  message: WorkspaceMessage,
  packet: AssistantPacket
): WorkspaceMessage {
  const packets = [...message.packets, packet];

  switch (packet.type) {
    case "message_start":
      return {
        ...message,
        packets,
        documents: dedupeDocuments([
          ...message.documents,
          ...(packet.final_documents ?? []),
        ]),
      };

    case "message_delta":
      return {
        ...message,
        packets,
        content: `${message.content}${packet.content}`,
      };

    case "citation_info":
      return {
        ...message,
        packets,
        citations: dedupeCitations([...message.citations, packet]),
      };

    case "search_tool_documents_delta":
    case "open_url_documents":
      return {
        ...message,
        packets,
        documents: dedupeDocuments([...message.documents, ...packet.documents]),
      };

    case "file_reader_result":
      return {
        ...message,
        packets,
        documents: dedupeDocuments([
          ...message.documents,
          {
            document_id: `file-reader:${packet.file_id}`,
            file_id: packet.file_id,
            title: packet.file_name,
            source: packet.file_name,
            section: "File Reader",
            content: packet.content,
            preview: packet.preview,
            score: 1,
          },
        ]),
      };

    default:
      return {
        ...message,
        packets,
      };
  }
}
