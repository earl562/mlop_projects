export function safeExternalHref(value: string): string | null {
  try {
    const url = new URL(value);
    if (isAllowedExternalProtocol(url.protocol)) return url.href;
  } catch {
    return null;
  }
  return null;
}

function isAllowedExternalProtocol(protocol: string): boolean {
  switch (protocol) {
    case "http:":
    case "https:":
      return true;
    default:
      return false;
  }
}
