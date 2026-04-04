import { AgentClient } from "@21st-sdk/node"

const client = new AgentClient({ apiKey: process.env.API_KEY_21ST! })

// Create a sandbox for an agent
const sandbox = await client.sandboxes.create({ agent: "my-agent" })

// Create a thread in the sandbox
const thread = await client.threads.create({
  sandboxId: sandbox.id,
  name: "Chat 1",
})

// Create a short-lived token for client-side use
const token = await client.tokens.create({ agent: "my-agent" })
