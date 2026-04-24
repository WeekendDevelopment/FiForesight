resource "upstash_redis_database" "redis" {
  database_name  = "fiforesight-redis"
  primary_region = "eu-west-2"
  tls            = true
  region         = "global"
}

output "redis_endpoint" {
  description = "Upstash Redis endpoint"
  value       = upstash_redis_database.redis.endpoint
}

output "redis_port" {
  description = "Upstash Redis port"
  value       = upstash_redis_database.redis.port
}

output "redis_password" {
  description = "Upstash Redis password"
  value       = upstash_redis_database.redis.password
  sensitive   = true
}

output "redis_url" {
  description = "Redis connection URL"
  value       = "rediss://default:${upstash_redis_database.redis.password}@${upstash_redis_database.redis.endpoint}:${upstash_redis_database.redis.port}"
  sensitive   = true
}
