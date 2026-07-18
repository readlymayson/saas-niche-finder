import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { Account } from "@/pages/Account"
import { AuthPage } from "@/pages/AuthPage"
import { BillingSuccess } from "@/pages/BillingSuccess"
import { Dashboard } from "@/pages/Dashboard"
import { Landing } from "@/pages/Landing"
import { NicheDetail } from "@/pages/NicheDetail"

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<AuthPage />} />
        <Route path="/register" element={<AuthPage />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/niche/:id" element={<NicheDetail />} />
        <Route path="/account" element={<Account />} />
        <Route path="/billing/success" element={<BillingSuccess />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
