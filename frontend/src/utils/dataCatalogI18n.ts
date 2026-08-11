import type { TFunction } from 'i18next';
import type { Catalog, CatalogField, DataResource } from '@/types/data';

/**
 * Catalog labels come from the backend whitelist, but the resource id is the
 * stable API contract. Translate by that id and keep the backend label as a
 * forward-compatible fallback for newly added resources.
 */
export const getCatalogResourceLabel = (t: TFunction, catalog: Catalog): string =>
  t(`data.catalog.resources.${catalog.resource}`, { defaultValue: catalog.label });

/** Translate field help by stable field name, with a resource-specific override. */
export const getCatalogFieldDescription = (
  t: TFunction,
  resource: DataResource,
  field: CatalogField,
): string =>
  t(
    [
      `data.catalog.fields.${resource}.${field.name}`,
      `data.catalog.fields.common.${field.name}`,
    ],
    { defaultValue: field.description },
  );
