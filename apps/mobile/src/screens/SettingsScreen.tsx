import type { HealthResponse } from "@drishti/contracts";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { fetchHealth } from "../api/client";
import { loadBackendUrl, normalizeBackendUrl, saveBackendUrl } from "../state/settings";

type CheckState =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "success"; health: HealthResponse }
  | { kind: "error"; message: string };

export function SettingsScreen({ onOpenCamera }: { onOpenCamera: (backendUrl: string) => void }) {
  const [backendUrl, setBackendUrl] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const [checkState, setCheckState] = useState<CheckState>({ kind: "idle" });

  useEffect(() => {
    loadBackendUrl().then(setBackendUrl).catch(() => setSaveMessage("Could not load saved settings."));
  }, []);

  const save = async () => {
    try {
      const normalized = await saveBackendUrl(backendUrl);
      setBackendUrl(normalized);
      setSaveMessage("Backend address saved on this phone.");
      setCheckState({ kind: "idle" });
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : "Could not save the address.");
    }
  };

  const checkConnection = async () => {
    setCheckState({ kind: "checking" });
    try {
      const normalized = normalizeBackendUrl(backendUrl);
      const health = await fetchHealth(normalized);
      setCheckState({ kind: "success", health });
    } catch (error) {
      setCheckState({
        kind: "error",
        message: error instanceof Error ? error.message : "Backend is unreachable.",
      });
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text accessibilityRole="header" style={styles.eyebrow}>DRISHTI</Text>
      <Text accessibilityRole="header" style={styles.title}>Local connection</Text>
      <Text style={styles.description}>
        Enter the laptop address shown on your private Wi-Fi or hotspot. DRISHTI does not use a cloud server.
      </Text>

      <Text style={styles.label}>Laptop backend address</Text>
      <TextInput
        accessibilityLabel="Laptop backend address"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        onChangeText={setBackendUrl}
        placeholder="http://192.168.1.10:8000"
        placeholderTextColor="#7890a4"
        style={styles.input}
        value={backendUrl}
      />

      <Pressable accessibilityRole="button" onPress={save} style={styles.primaryButton}>
        <Text style={styles.primaryButtonText}>Save address</Text>
      </Pressable>
      <Pressable accessibilityRole="button" onPress={checkConnection} style={styles.secondaryButton}>
        <Text style={styles.secondaryButtonText}>Check connection</Text>
      </Pressable>

      {saveMessage ? <Text accessibilityLiveRegion="polite" style={styles.message}>{saveMessage}</Text> : null}
      <ConnectionResult state={checkState} />

      {checkState.kind === "success" ? (
        <Pressable
          accessibilityRole="button"
          onPress={() => onOpenCamera(normalizeBackendUrl(backendUrl))}
          style={styles.secondaryButton}
        >
          <Text style={styles.secondaryButtonText}>Open Phase 1 camera test</Text>
        </Pressable>
      ) : null}

      <View style={styles.notice}>
        <Text style={styles.noticeTitle}>Backend test harness only</Text>
        <Text style={styles.noticeText}>Phase 1 sends individual camera frames for backend and coordinate verification. It is not the production mobile application.</Text>
      </View>
    </ScrollView>
  );
}

function ConnectionResult({ state }: { state: CheckState }) {
  if (state.kind === "idle") return null;
  if (state.kind === "checking") {
    return <ActivityIndicator accessibilityLabel="Checking connection" color="#5ee2a0" size="large" />;
  }
  if (state.kind === "error") {
    return <Text accessibilityLiveRegion="assertive" style={styles.error}>Not connected: {state.message}</Text>;
  }
  return (
    <View accessibilityLiveRegion="polite" style={styles.success}>
      <Text style={styles.successTitle}>Backend connected</Text>
      <Text style={styles.successText}>Service: {state.health.status}</Text>
      <Text style={styles.successText}>Database: {state.health.database.status}</Text>
      <Text style={styles.successText}>Walk Mode: unavailable; Phase 1 test only</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, backgroundColor: "#071a2b", padding: 24, gap: 16 },
  eyebrow: { color: "#5ee2a0", fontSize: 18, fontWeight: "800", letterSpacing: 2 },
  title: { color: "#ffffff", fontSize: 34, fontWeight: "800" },
  description: { color: "#c7d7e5", fontSize: 19, lineHeight: 28 },
  label: { color: "#ffffff", fontSize: 18, fontWeight: "700", marginTop: 8 },
  input: { backgroundColor: "#102d43", borderColor: "#52738d", borderRadius: 12, borderWidth: 2, color: "#ffffff", fontSize: 18, minHeight: 58, paddingHorizontal: 16 },
  primaryButton: { alignItems: "center", backgroundColor: "#5ee2a0", borderRadius: 12, minHeight: 58, justifyContent: "center" },
  primaryButtonText: { color: "#062019", fontSize: 19, fontWeight: "800" },
  secondaryButton: { alignItems: "center", borderColor: "#5ee2a0", borderRadius: 12, borderWidth: 2, minHeight: 58, justifyContent: "center" },
  secondaryButtonText: { color: "#ffffff", fontSize: 19, fontWeight: "800" },
  message: { color: "#c7d7e5", fontSize: 17 },
  error: { backgroundColor: "#4a1721", borderRadius: 12, color: "#ffd8df", fontSize: 18, padding: 16 },
  success: { backgroundColor: "#0d3a2c", borderRadius: 12, gap: 5, padding: 16 },
  successTitle: { color: "#8ff4bd", fontSize: 20, fontWeight: "800" },
  successText: { color: "#e1fff0", fontSize: 17 },
  notice: { backgroundColor: "#102d43", borderRadius: 12, marginTop: 8, padding: 16 },
  noticeTitle: { color: "#ffffff", fontSize: 18, fontWeight: "800" },
  noticeText: { color: "#c7d7e5", fontSize: 16, lineHeight: 23, marginTop: 6 },
});
