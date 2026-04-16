/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Pencil, Plus, Trash2 } from "lucide-react";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TIssueType } from "@plane/types";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
import { useUserPermissions } from "@/hooks/store/user";
// services
import { IssuePropertyService } from "@/services/issue/issue_property.service";
// local imports
import type { Route } from "./+types/page";
import { IssueTypesWorkspaceSettingsHeader } from "./header";

const issuePropertyService = new IssuePropertyService();

const WorkspaceIssueTypesSettingsPage = observer(function WorkspaceIssueTypesSettingsPage({
  params,
}: Route.ComponentProps) {
  const { workspaceSlug } = params;
  const { t } = useTranslation();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { currentWorkspace } = useWorkspace();

  const [issueTypes, setIssueTypes] = useState<TIssueType[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const canPerformAdminActions = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);

  const fetchIssueTypes = useCallback(async () => {
    try {
      const types = await issuePropertyService.getWorkspaceIssueTypes(workspaceSlug);
      setIssueTypes(types);
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error",
        message: t("workspace_settings.settings.issue_types.toasts.error"),
      });
    } finally {
      setLoading(false);
    }
  }, [workspaceSlug, t]);

  useEffect(() => {
    fetchIssueTypes();
  }, [fetchIssueTypes]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await issuePropertyService.createIssueType(workspaceSlug, { name: newName.trim() });
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("workspace_settings.settings.issue_types.toasts.created") });
      setNewName("");
      setIsCreating(false);
      fetchIssueTypes();
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error",
        message: t("workspace_settings.settings.issue_types.toasts.error"),
      });
    }
  };

  const handleUpdate = async (id: string) => {
    if (!editName.trim()) return;
    try {
      await issuePropertyService.updateIssueType(workspaceSlug, id, { name: editName.trim() });
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("workspace_settings.settings.issue_types.toasts.updated") });
      setEditingId(null);
      fetchIssueTypes();
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error",
        message: t("workspace_settings.settings.issue_types.toasts.error"),
      });
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(t("workspace_settings.settings.issue_types.delete_confirm"))) return;
    try {
      await issuePropertyService.deleteIssueType(workspaceSlug, id);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("workspace_settings.settings.issue_types.toasts.deleted") });
      fetchIssueTypes();
    } catch (error: any) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error",
        message: error?.error || t("workspace_settings.settings.issue_types.toasts.error"),
      });
    }
  };

  const startEdit = (issueType: TIssueType) => {
    setEditingId(issueType.id);
    setEditName(issueType.name);
  };

  const pageTitle = currentWorkspace?.name ? `${currentWorkspace.name} - Issue Types` : undefined;

  if (workspaceUserInfo && !canPerformAdminActions) {
    return <NotAuthorizedView section="settings" className="h-auto" />;
  }

  return (
    <SettingsContentWrapper header={<IssueTypesWorkspaceSettingsHeader />} hugging>
      <PageHead title={pageTitle} />
      <section className="size-full">
        <div className="flex items-center justify-between gap-4 pb-3.5">
          <div>
            <h4 className="text-h3-medium">{t("workspace_settings.settings.issue_types.heading")}</h4>
            <p className="mt-1 text-body-sm-regular text-secondary">
              {t("workspace_settings.settings.issue_types.description")}
            </p>
          </div>
          {canPerformAdminActions && !isCreating && (
            <Button
              variant="primary"
              size="lg"
              onClick={() => setIsCreating(true)}
              prependIcon={<Plus className="size-4" />}
            >
              {t("workspace_settings.settings.issue_types.add_type")}
            </Button>
          )}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-10 text-secondary">Loading...</div>
        ) : (
          <div className="space-y-2">
            {isCreating && (
              <div className="flex items-center gap-2 rounded-md border border-subtle bg-surface-1 px-3 py-2">
                <input
                  className="flex-1 border-none bg-transparent text-body-sm-regular outline-none placeholder:text-placeholder"
                  placeholder={t("workspace_settings.settings.issue_types.name_placeholder")}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCreate();
                    if (e.key === "Escape") {
                      setIsCreating(false);
                      setNewName("");
                    }
                  }}
                  // eslint-disable-next-line jsx-a11y/no-autofocus
                  autoFocus
                />
                <Button variant="primary" size="sm" onClick={handleCreate}>
                  {t("workspace_settings.settings.issue_types.save")}
                </Button>
                <Button
                  variant="neutral-primary"
                  size="sm"
                  onClick={() => {
                    setIsCreating(false);
                    setNewName("");
                  }}
                >
                  {t("workspace_settings.settings.issue_types.cancel")}
                </Button>
              </div>
            )}

            {issueTypes.map((issueType) => (
              <div
                key={issueType.id}
                className="flex items-center justify-between rounded-md border border-subtle bg-surface-1 px-3 py-2.5"
              >
                {editingId === issueType.id ? (
                  <div className="flex flex-1 items-center gap-2">
                    <input
                      className="flex-1 border-none bg-transparent text-body-sm-regular outline-none"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleUpdate(issueType.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      // eslint-disable-next-line jsx-a11y/no-autofocus
                      autoFocus
                    />
                    <Button variant="primary" size="sm" onClick={() => handleUpdate(issueType.id)}>
                      {t("workspace_settings.settings.issue_types.save")}
                    </Button>
                    <Button variant="neutral-primary" size="sm" onClick={() => setEditingId(null)}>
                      {t("workspace_settings.settings.issue_types.cancel")}
                    </Button>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-2">
                      <span className="text-body-sm-medium">{issueType.name}</span>
                      {issueType.is_default && (
                        <span className="rounded bg-layer-transparent-selected px-1.5 py-0.5 text-body-xs-regular text-secondary">
                          Default
                        </span>
                      )}
                      {issueType.is_epic && (
                        <span className="rounded bg-layer-transparent-selected px-1.5 py-0.5 text-body-xs-regular text-secondary">
                          Epic
                        </span>
                      )}
                    </div>
                    {canPerformAdminActions && (
                      <div className="flex items-center gap-1">
                        <button
                          className="rounded p-1 text-secondary hover:bg-layer-transparent-hover hover:text-primary"
                          onClick={() => startEdit(issueType)}
                        >
                          <Pencil className="size-3.5" />
                        </button>
                        {!issueType.is_default && (
                          <button
                            className="hover:text-red-500 rounded p-1 text-secondary hover:bg-layer-transparent-hover"
                            onClick={() => handleDelete(issueType.id)}
                          >
                            <Trash2 className="size-3.5" />
                          </button>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}

            {issueTypes.length === 0 && !isCreating && (
              <div className="flex flex-col items-center justify-center py-10 text-secondary">
                <p className="text-body-sm-regular">No issue types found.</p>
              </div>
            )}
          </div>
        )}
      </section>
    </SettingsContentWrapper>
  );
});

export default WorkspaceIssueTypesSettingsPage;
