import AsyncStorage from "@react-native-async-storage/async-storage";

const BACKEND_URL_KEY = "drishti.backend_url.v1";

function isPrivateIpv4(hostname: string): boolean {
  const parts = hostname.split(".").map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return false;
  }
  return (
    parts[0] === 10 ||
    (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
    (parts[0] === 192 && parts[1] === 168) ||
    parts[0] === 127
  );
}

export function normalizeBackendUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error("Enter the laptop's private network address.");
  }

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error("Use a full address such as http://192.168.1.10:8000.");
  }

  const isLocalHost = parsed.hostname === "localhost" || isPrivateIpv4(parsed.hostname);
  if (parsed.protocol !== "http:" || !isLocalHost || parsed.username || parsed.password) {
    throw new Error("Use an HTTP address on localhost or a private IPv4 network.");
  }
  if (parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new Error("Enter only the backend base address, without a path or query.");
  }

  return parsed.origin;
}

export async function loadBackendUrl(): Promise<string> {
  return (await AsyncStorage.getItem(BACKEND_URL_KEY)) ?? "";
}

export async function saveBackendUrl(value: string): Promise<string> {
  const normalized = normalizeBackendUrl(value);
  await AsyncStorage.setItem(BACKEND_URL_KEY, normalized);
  return normalized;
}
