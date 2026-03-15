/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { FC } from "react";
import { observer } from "mobx-react";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent } from "@/components/issues/issue-detail/issue-activity/activity/actions/helpers/activity-block";

type TIssueAdditionalPropertiesActivity = {
  activityId: string;
  ends: "top" | "bottom" | undefined;
};

export const IssueAdditionalPropertiesActivity: FC<TIssueAdditionalPropertiesActivity> = observer(
  function IssueAdditionalPropertiesActivity({ activityId, ends }) {
    const {
      activity: { getActivityById },
    } = useIssueDetail();

    const activity = getActivityById(activityId);
    if (!activity) return <></>;

    const fieldName = activity.field ?? "property";
    const newValue = activity.new_value ?? "—";
    const oldValue = activity.old_value;

    return (
      <IssueActivityBlockComponent activityId={activityId} ends={ends}>
        <>
          updated <span className="font-medium text-primary">{fieldName}</span>
          {oldValue ? (
            <>
              {" "}
              from <span className="font-medium text-primary">{oldValue}</span>
            </>
          ) : null}{" "}
          to <span className="font-medium text-primary">{newValue}</span>.
        </>
      </IssueActivityBlockComponent>
    );
  }
);
