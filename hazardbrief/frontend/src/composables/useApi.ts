import axios from "axios";
import type { HazardData } from "../types/hazard";
import type { HazardReport } from "../types/report";
import type { Company, Property, PropertyCreate } from "../types/property";

const api = axios.create({
	baseURL: import.meta.env.VITE_API_BASE || "",
	timeout: 30000,
});

export const useApi = () => ({
	// ── 物件 ──────────────────────────────────────────────────────────
	getProperties: (companyId?: string): Promise<Property[]> =>
		api
			.get("/api/properties", { params: companyId ? { company_id: companyId } : undefined })
			.then((r) => r.data),

	getProperty: (id: string): Promise<Property> =>
		api.get(`/api/properties/${id}`).then((r) => r.data),

	createProperty: (data: PropertyCreate): Promise<Property> =>
		api.post("/api/properties", data).then((r) => r.data),

	deleteProperty: (id: string): Promise<{ property_id: string; status: string }> =>
		api.delete(`/api/properties/${id}`).then((r) => r.data),

	// ── ハザードデータ ────────────────────────────────────────────────
	getHazard: (propertyId: string, forceRefresh = false): Promise<HazardData> =>
		api
			.get(`/api/hazard/${propertyId}`, {
				params: forceRefresh ? { force_refresh: true } : undefined,
			})
			.then((r) => r.data),

	// ── レポート ──────────────────────────────────────────────────────
	getReport: (propertyId: string): Promise<HazardReport> =>
		api.get(`/api/report/${propertyId}`).then((r) => r.data),

	// ── 会社 ──────────────────────────────────────────────────────────
	getCompanies: (): Promise<Company[]> =>
		api.get("/api/companies").then((r) => r.data),

	getCompany: (id: string): Promise<Company> =>
		api.get(`/api/companies/${id}`).then((r) => r.data),

	createCompany: (name: string, plan = "free"): Promise<Company> =>
		api.post("/api/companies", { name, plan }).then((r) => r.data),
});
