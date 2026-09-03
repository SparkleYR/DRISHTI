import AsyncStorage from "@react-native-async-storage/async-storage";

import { loadBackendUrl, normalizeBackendUrl, saveBackendUrl } from "../state/settings";

beforeEach(async () => {
  await AsyncStorage.clear();
});

test.each([
  ["http://192.168.1.10:8000", "http://192.168.1.10:8000"],
  [" http://10.0.0.5:8000/ ", "http://10.0.0.5:8000"],
  ["http://172.16.0.1:8000", "http://172.16.0.1:8000"],
  ["http://localhost:8000", "http://localhost:8000"],
])("normalizes an allowed local URL", (input, expected) => {
  expect(normalizeBackendUrl(input)).toBe(expected);
});

test.each([
  "https://example.com",
  "http://8.8.8.8:8000",
  "ftp://192.168.1.10",
  "http://user:secret@192.168.1.10:8000",
  "http://192.168.1.10:8000/api/v1/health",
])("rejects a non-local or non-base URL", (input) => {
  expect(() => normalizeBackendUrl(input)).toThrow();
});

test("persists the normalized backend URL", async () => {
  await saveBackendUrl(" http://192.168.137.1:8000/ ");

  await expect(loadBackendUrl()).resolves.toBe("http://192.168.137.1:8000");
});
