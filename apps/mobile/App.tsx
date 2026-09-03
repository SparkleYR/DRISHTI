import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { SafeAreaView, StyleSheet } from "react-native";

import { CameraTestScreen } from "./src/screens/CameraTestScreen";
import { SettingsScreen } from "./src/screens/SettingsScreen";

export default function App() {
  const [cameraBackendUrl, setCameraBackendUrl] = useState<string | null>(null);
  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="light" />
      {cameraBackendUrl ? (
        <CameraTestScreen backendUrl={cameraBackendUrl} onBack={() => setCameraBackendUrl(null)} />
      ) : (
        <SettingsScreen onOpenCamera={setCameraBackendUrl} />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#071a2b",
  },
});
