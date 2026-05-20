import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'shortLinkManagement_columnVisibility';

export function useShortLinkColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      short_code: true,
      short_url: true,
      original_url: true,
      title: true,
      description: true,
      offer_id: true,
      channel_id: true,
      creator_name: true,
      click_count: true,
      show_count: true,
      expires_at: true,
      is_active: true,
      created_at: true,
    }),
    getSavableColumns: (v) => ({
      id: v.id,
      original_url: v.original_url,
      title: v.title,
      description: v.description,
      offer_id: v.offer_id,
      channel_id: v.channel_id,
      creator_name: v.creator_name,
      click_count: v.click_count,
      show_count: v.show_count,
      expires_at: v.expires_at,
      is_active: v.is_active,
      created_at: v.created_at,
    }),
    pinColumns: ['short_code', 'short_url'],
  });
}
