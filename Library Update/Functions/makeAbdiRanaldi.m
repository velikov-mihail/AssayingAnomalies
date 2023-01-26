function chl=makeAbdiRanaldi()
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% This function creates the CHL Effective Spread (!!!) measure from Abdi
% and Ranaldo (RFS, 2017).

tic;
fprintf('Starting CHL construction at:\n');
disp(datetime('now'));

load dbidlo
load daskhi
dhigh=dbidlo;
dlow=daskhi;
clear dbidlo daskhi
load dprc
load ddates
load dates
load ret


dprc_raw=dprc;
dhigh(dprc<0 | isnan(dprc))=nan;
dlow(dprc<0 | isnan(dprc))=nan;

for i=2:length(ddates)
    ind=isnan(dprc(i,:)) & isfinite(dprc(i-1,:));
    dprc(i,ind)=dprc(i-1,ind);
    ind=isnan(dhigh(i,:)) & isfinite(dhigh(i-1,:));
    dhigh(i,ind)=dhigh(i-1,ind);
    ind=isnan(dlow(i,:)) & isfinite(dlow(i-1,:));
    dlow(i,ind)=dlow(i-1,ind);    
end

dprc=abs(dprc);

s=find(dates==floor(ddates(1)/100));

midpoint=(log(dlow)+log(dhigh))/2;
midpoint_tp1=lead(midpoint,1,nan);


clear dhigh dlow
load dbidlo
load daskhi

dbidlo(dprc_raw<0 | isnan(dprc_raw))=nan;
daskhi(dprc_raw<0 | isnan(dprc_raw))=nan;

chl=nan(size(ret));

for i=s:length(dates)
    month_ind=find(floor(ddates/100)==dates(i));
    hor_ind=find(sum( dprc_raw(month_ind,:)>0   & ...
                      isfinite(dprc_raw(month_ind,:)) & ...
                      isfinite(dbidlo(month_ind,:)) & ...
                      isfinite(daskhi(month_ind,:)) & ...
                      daskhi(month_ind,:)-dbidlo(month_ind,:)~=0 ...
                      ,1)>=12);
                      
    eta_tp1=midpoint_tp1(month_ind,hor_ind);
    eta_t=midpoint(month_ind,hor_ind);
    c_t=log(dprc(month_ind,hor_ind));
    
    s_hat_t=sqrt(max(4*(c_t-eta_t).*(c_t-eta_tp1),0));
    chl(i,hor_ind)=nanmean(s_hat_t,1);
end

fprintf('Done with CHL at:\n');
disp(datetime('now'));
toc;
