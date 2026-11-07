import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/context/AuthContext";
import AppLayout from "@/components/AppLayout";
import Login from "@/pages/Login";
import Home from "@/pages/Home";
import Transactions from "@/pages/Transactions";
import Payments from "@/pages/Payments";
import Documents from "@/pages/Documents";
import Checks from "@/pages/Checks";
import Forensics from "@/pages/Forensics";
import Activity from "@/pages/Activity";
import SettingsPage from "@/pages/Settings";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<AppLayout />}>
            <Route index element={<Home />} />
            <Route path="deals" element={<Transactions />} />
            <Route path="payments" element={<Payments />} />
            <Route path="documents" element={<Documents />} />
            <Route path="checks" element={<Checks />} />
            <Route path="forensics" element={<Forensics />} />
            <Route path="activity" element={<Activity />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster theme="dark" position="top-right" richColors closeButton />
    </AuthProvider>
  );
}

export default App;
