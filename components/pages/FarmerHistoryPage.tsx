"use client";

import { useEffect, useState } from "react";
import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchFarmerWorkspace, upsertUser, searchFarmers, addFarm } from "@/lib/api";
import type { FarmerWorkspace, FarmerSearchResult } from "@/lib/types";

export function FarmerHistoryPage() {
  const { t, language } = useLanguage();
  const { activeFarmer, setActiveFarmer, clearActiveFarmer } = useFarmerSession();
  const [activeTab, setActiveTab] = useState<"find" | "register" | "profile">(
    activeFarmer ? "profile" : "find"
  );
  const [workspace, setWorkspace] = useState<FarmerWorkspace | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  
  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<FarmerSearchResult[]>([]);
  
  const [form, setForm] = useState({
    farmer_id: "",
    name: "",
    mobile: "",
    state: "",
    district: "",
    farm_name: "",
    village: "",
    acres: 1,
    primary_crop: "wheat",
    soil_type: "loam",
    irrigation_source: "Canal"
  });

  useEffect(() => {
    if (!activeFarmer) {
      setWorkspace(null);
      if (activeTab === "profile") setActiveTab("find");
      return;
    }

    void fetchFarmerWorkspace(activeFarmer.farmer_id).then((data) => {
      setWorkspace(data);
      setForm((prev) => ({
        ...prev,
        farmer_id: data.profile.farmer_id,
        name: data.profile.name,
        mobile: data.profile.mobile,
        state: data.profile.state ?? "",
        district: data.profile.district ?? "",
        farm_name: data.farms[0]?.farm_name ?? prev.farm_name,
        village: data.farms[0]?.village ?? prev.village,
        acres: data.farms[0]?.acres ?? prev.acres,
        primary_crop: data.farms[0]?.primary_crop ?? prev.primary_crop,
        soil_type: data.farms[0]?.soil_type ?? prev.soil_type,
        irrigation_source: data.farms[0]?.irrigation_source ?? prev.irrigation_source
      }));
    });
  }, [activeFarmer]);

  function generateId() {
    const s = () => Math.random().toString(36).substring(2, 6).toUpperCase();
    return `REG-${s()}-${s()}`;
  }

  function handleCopy(id: string) {
    navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleSearch() {
    if (!searchQuery.trim()) return;
    setBusy(true);
    setSearchResults([]); // Clear previous results
    try {
      const results = await searchFarmers(searchQuery);
      setSearchResults(results);
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    setBusy(true);
    try {
      const finalId = form.farmer_id.trim() || generateId();
      
      const profile = await upsertUser({
        farmer_id: finalId,
        name: form.name,
        mobile: form.mobile,
        state: form.state,
        district: form.district,
        language
      });

      await addFarm({
        farmer_id: profile.farmer_id,
        mobile: profile.mobile,
        farm_name: form.farm_name,
        village: form.village,
        district: form.district,
        state: form.state,
        acres: form.acres,
        primary_crop: form.primary_crop,
        soil_type: form.soil_type,
        irrigation_source: form.irrigation_source
      });

      setActiveFarmer(profile);
      setActiveTab("profile");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.history")}
        title="Farmer Portal"
        description="A unified agricultural identity and record management system."
      />

      <div className="portal-container mt-8">
        <main className="w-full">
          {/* Tabs Navigation */}
          <nav className="portal-tabs">
            <button
              className={`portal-tab-btn ${activeTab === "find" ? "active" : ""}`}
              onClick={() => setActiveTab("find")}
            >
              {t("common.search")}
            </button>
            <button
              className={`portal-tab-btn ${activeTab === "register" ? "active" : ""}`}
              onClick={() => setActiveTab("register")}
            >
              {t("farmer.createTitle")}
            </button>
            <button
              className={`portal-tab-btn ${activeTab === "profile" ? "active" : ""}`}
              disabled={!activeFarmer}
              onClick={() => setActiveTab("profile")}
            >
              {t("history.title")}
            </button>
          </nav>

          <section className="portal-tab-content">
            {activeTab === "find" && (
              <article className="surface-card">
                <h3 className="section-title mb-6">{t("shell.searchFarmers")}</h3>
                <div className="search-panel-airy">
                  <div className="field">
                    <span>{t("common.search")}</span>
                    <div className="search-input-group">
                      <input
                        className="airy-input"
                        placeholder={t("shell.searchPlaceholder")}
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                      />
                      <button className="primary-btn" onClick={handleSearch} disabled={busy}>
                        {busy ? "..." : t("common.search")}
                      </button>
                    </div>
                  </div>

                  {searchResults.length > 0 ? (
                    <div className="search-results-list mt-6">
                      {searchResults.map((farmer: FarmerSearchResult) => (
                        <div 
                          key={farmer.farmer_id} 
                          className={`search-result-card ${farmer.farmer_id === activeFarmer?.farmer_id ? 'active' : ''}`}
                        >
                          <div className="result-info">
                            <div className="flex items-center gap-2">
                              <strong>{farmer.name}</strong>
                              {farmer.farmer_id === activeFarmer?.farmer_id && (
                                <span className="badge badge-accent text-[10px] py-0 px-1">Active</span>
                              )}
                            </div>
                            <span>{farmer.farmer_id} • {farmer.mobile}</span>
                            {farmer.village && <span className="text-xs text-muted block">{farmer.village}, {farmer.district}</span>}
                          </div>
                          <button
                            className="select-pill"
                            onClick={() => {
                              setActiveFarmer(farmer);
                              setActiveTab("profile");
                            }}
                            disabled={farmer.farmer_id === activeFarmer?.farmer_id}
                          >
                            {farmer.farmer_id === activeFarmer?.farmer_id ? t("common.activeFarmer") : t("common.select")}
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    searchQuery && !busy && (
                      <div className="empty-state-airy mt-6">
                        <div className="text-2xl mb-2">🔍</div>
                        <p>{t("shell.noSearchResults")}</p>
                      </div>
                    )
                  )}
                </div>
              </article>
            )}

            {activeTab === "register" && (
              <article className="surface-card">
                <div className="flex justify-between items-center mb-8">
                  <div>
                    <h3 className="section-title mb-1">{t("farmer.createTitle")}</h3>
                    <p className="text-sm text-muted">{t("farmer.createBody")}</p>
                  </div>
                  <div className="badge badge-accent">Secure Portal</div>
                </div>

                <div className="registration-flow">
                  <div className="airy-portal-grid">
                    <div className="portal-form-group">
                      <div className="form-header-with-icon">
                        <div className="crop-icon-wrapper" style={{ fontSize: '1.2rem', padding: '0.8rem' }}>👤</div>
                        <h4 className="tips-title mb-0">{t("history.profile")}</h4>
                      </div>
                      
                      <div className="form-stack space-y-4">
                        <label className="field">
                          <span>{t("farmer.name")}</span>
                          <input
                            className="airy-input"
                            value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                            placeholder="Full Name (e.g. Adarsh Kumar)"
                            style={{ padding: '1.2rem' }}
                          />
                        </label>
                        <label className="field">
                          <span>{t("farmer.mobile")}</span>
                          <input
                            className="airy-input"
                            value={form.mobile}
                            onChange={(e) => setForm({ ...form, mobile: e.target.value })}
                            placeholder="10-digit primary mobile"
                            style={{ padding: '1.2rem' }}
                          />
                        </label>
                        <div className="grid grid-cols-2 gap-6">
                          <label className="field">
                            <span>{t("farmer.state")}</span>
                            <input
                              className="airy-input"
                              value={form.state}
                              onChange={(e) => setForm({ ...form, state: e.target.value })}
                              style={{ padding: '1.2rem' }}
                            />
                          </label>
                          <label className="field">
                            <span>{t("farmer.district")}</span>
                            <input
                              className="airy-input"
                              value={form.district}
                              onChange={(e) => setForm({ ...form, district: e.target.value })}
                              style={{ padding: '1.2rem' }}
                            />
                          </label>
                        </div>
                      </div>
                    </div>

                    <div className="portal-form-group">
                      <div className="form-header-with-icon">
                        <div className="crop-icon-wrapper" style={{ fontSize: '1.2rem', padding: '0.8rem' }}>🚜</div>
                        <h4 className="tips-title mb-0">{t("history.farms")}</h4>
                      </div>

                      <div className="form-stack space-y-4">
                        <label className="field">
                          <span>{t("farmer.farmName")}</span>
                          <input
                            className="airy-input"
                            value={form.farm_name}
                            onChange={(e) => setForm({ ...form, farm_name: e.target.value })}
                            placeholder="e.g. West Highlands Farm"
                            style={{ padding: '1.2rem' }}
                          />
                        </label>
                        <div className="grid grid-cols-2 gap-6">
                          <label className="field">
                            <span>{t("farmer.farmSize")} (Acres)</span>
                            <input
                              type="number"
                              className="airy-input"
                              value={form.acres}
                              onChange={(e) => setForm({ ...form, acres: Number(e.target.value) })}
                              style={{ padding: '1.2rem' }}
                            />
                          </label>
                          <label className="field">
                            <span>{t("farmer.crop")}</span>
                            <input
                              className="airy-input"
                              value={form.primary_crop}
                              onChange={(e) => setForm({ ...form, primary_crop: e.target.value })}
                              style={{ padding: '1.2rem' }}
                            />
                          </label>
                        </div>
                        <label className="field">
                          <span>{t("farmer.village")} / Location</span>
                          <input
                            className="airy-input"
                            value={form.village}
                            onChange={(e) => setForm({ ...form, village: e.target.value })}
                            placeholder="Village or Block name"
                            style={{ padding: '1.2rem' }}
                          />
                        </label>
                      </div>
                    </div>
                  </div>

                  <div className="mt-12 pt-8 border-t border-line flex justify-end">
                    <button className="primary-btn px-16 py-4 text-lg" onClick={handleSave} disabled={busy}>
                      {busy ? t("common.loading") : t("common.save")}
                    </button>
                  </div>
                </div>
              </article>
            )}

            {activeTab === "profile" && activeFarmer && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <aside className="lg:col-span-1">
                  <article className="surface-card">
                    <h3 className="section-title mb-6">{t("common.activeFarmer")}</h3>
                    <div className="active-profile-summary">
                      <div className="id-badge-container mb-6">
                        <div className="flex flex-col">
                          <span className="id-badge-label">{t("farmer.id")}</span>
                          <span className="id-value">{activeFarmer.farmer_id}</span>
                        </div>
                        <button className="copy-btn" onClick={() => handleCopy(activeFarmer.farmer_id)}>
                          {copied ? "✓" : "❐"}
                        </button>
                        {copied && <div className="success-toast">Copied!</div>}
                      </div>

                      <div className="profile-brief mb-6">
                        <p className="farmer-name text-2xl mb-1">{activeFarmer.name}</p>
                        <p className="text-muted">{activeFarmer.mobile} • {activeFarmer.district}</p>
                      </div>

                      <div className="flex gap-2">
                        <button className="ghost-btn w-full" onClick={() => clearActiveFarmer()}>
                          {t("shell.clearFarmer")}
                        </button>
                      </div>
                    </div>
                  </article>

                  <article className="surface-card bg-brand-subtle mt-6">
                    <h4 className="font-bold text-brand mb-4">{t("dashboard.quickInsights")}</h4>
                    <div className="flex justify-between py-2 border-b border-brand border-opacity-10">
                      <span className="text-sm">{t("dashboard.totalFarms")}</span>
                      <strong>{workspace?.farms.length ?? 0}</strong>
                    </div>
                    <div className="flex justify-between py-2">
                      <span className="text-sm">{t("dashboard.savedRecords")}</span>
                      <strong>{workspace?.advisories.length ?? 0}</strong>
                    </div>
                  </article>
                </aside>

                <main className="lg:col-span-2 space-y-6">
                  <article className="surface-card min-h-[400px]">
                    <div className="flex justify-between items-center mb-8">
                      <h3 className="section-title mb-0">{t("history.advisories")}</h3>
                      <div className="badge badge-brand">LIVE DATA</div>
                    </div>

                    {workspace?.advisories && workspace.advisories.length > 0 ? (
                      <div className="records-list">
                        {workspace.advisories.map((item: any) => (
                          <div key={item.id} className="record-item hover:bg-slate-50 transition-colors">
                            <div className="record-info">
                              <div className="flex items-center gap-3">
                                <span className="badge badge-accent text-[10px]">
                                  {item.module.toUpperCase()}
                                </span>
                                <p className="record-title">{item.summary}</p>
                              </div>
                              <p className="text-xs text-muted mt-2 ml-[64px]">
                                {new Date(item.created_at).toLocaleString()}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-20 bg-subtle rounded-xl border-2 border-dashed border-line-strong">
                        <p className="text-2xl mb-2">🌾</p>
                        <p className="muted-copy">No advisory records found.</p>
                      </div>
                    )}
                  </article>
                </main>
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
