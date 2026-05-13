import { Route, Routes } from "react-router-dom";
import Sidebar from "./components/layout/Sidebar";
import Overview from "./pages/Overview";
import Invoices from "./pages/Invoices";
import Reconciliation from "./pages/Reconciliation";
import Tax from "./pages/Tax";
import ReviewQueue from "./pages/ReviewQueue";
import Ledger from "./pages/Ledger";
import Documents from "./pages/Documents";

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-slate-950">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/invoices" element={<Invoices />} />
          <Route path="/reconcile" element={<Reconciliation />} />
          <Route path="/tax" element={<Tax />} />
          <Route path="/review" element={<ReviewQueue />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/documents" element={<Documents />} />
        </Routes>
      </main>
    </div>
  );
}
