/**
 * 物件型定義
 */
export interface Property {
	id: string;
	company_id: string | null;
	created_by: string | null;
	address: string;
	latitude: number | null;
	longitude: number | null;
	property_name: string | null;
	notes: string | null;
	created_at: string;
}

export interface PropertyCreate {
	address: string;
	property_name?: string;
	notes?: string;
	company_id?: string;
	latitude?: number;
	longitude?: number;
}

export interface Company {
	id: string;
	name: string;
	plan: "free" | "standard" | "enterprise";
	created_at: string;
}
