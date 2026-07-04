#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { SafrStack } from "../lib/safr-stack";

const app = new cdk.App();
new SafrStack(app, "SafrOnAws", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || "ap-southeast-1",
  },
  description: "SAFR (Safeguards for Agentic Finance at Runtime) — all 5 components",
});
