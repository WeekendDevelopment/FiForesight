'use client';

import { Box, Card, CardContent, Grid, Skeleton, Stack } from '@mui/material';

export function ChartSkeleton() {
  return (
    <Card>
      <CardContent sx={{ p: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
          <Box>
            <Skeleton variant="text" width={120} height={48} />
            <Skeleton variant="text" width={180} height={24} />
          </Box>
          <Box sx={{ textAlign: 'right' }}>
            <Skeleton variant="text" width={100} height={48} />
            <Skeleton variant="text" width={80} height={20} />
          </Box>
        </Box>
        <Stack direction="row" spacing={3} sx={{ mb: 3 }}>
          {[1,2,3,4,5,6].map(i => (
            <Box key={i}><Skeleton variant="text" width={60} height={14} /><Skeleton variant="text" width={70} height={22} /></Box>
          ))}
        </Stack>
        <Skeleton variant="rectangular" height={420} sx={{ borderRadius: 2 }} />
      </CardContent>
    </Card>
  );
}

export function SidebarSkeleton() {
  return (
    <Stack spacing={3}>
      <Card><CardContent>
        <Skeleton variant="text" width="60%" height={20} />
        <Skeleton variant="rectangular" height={140} sx={{ mt: 2, borderRadius: 2 }} />
        <Skeleton variant="text" width="90%" height={16} sx={{ mt: 2 }} />
        <Skeleton variant="text" width="80%" height={16} />
      </CardContent></Card>
      <Card><CardContent>
        <Skeleton variant="text" width="50%" height={20} />
        <Grid container spacing={2} sx={{ mt: 1 }}>
          {[1,2,3,4,5,6,7,8].map(i => (
            <Grid size={6} key={i}>
              <Skeleton variant="text" width="80%" height={14} />
              <Skeleton variant="text" width="60%" height={22} />
            </Grid>
          ))}
        </Grid>
      </CardContent></Card>
    </Stack>
  );
}
