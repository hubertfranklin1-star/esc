import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/context/AuthContext";
import AppLayout from "@/components/AppLayout";
import Login from "@/pages/Login";
import Overview from "@/pages/Overview";
import Transactions from "@/pages/Transactions";
import Participants from "@/pages/Participants";
import Onboarding from "@/pages/Onboarding";
import Compliance from "@/pages/Compliance";
import Explorer from "@/pages/Explorer";
import Invoices from "@/pages/Invoices";
import Reports from "@/pages/Reports";
import Settlement from "@/pages/Settlement";
import AuditLogs from "@/pages/AuditLogs";
import SettingsPage from "@/pages/Settings";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<AppLayout />}>
            <Route index element={<Overview />} />
            <Route path="transactions" element={<Transactions />} />
            <Route path="participants" element={<Participants />} />
            <Route path="onboarding" element={<Onboarding />} />
            <Route path="compliance" element={<Compliance />} />
            <Route path="explorer" element={<Explorer />} />
            <Route path="invoices" element={<Invoices />} />
            <Route path="reports" element={<Reports />} />
            <Route path="settlement" element={<Settlement />} />
            <Route path="audit" element={<AuditLogs />} />
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
