% PURPOSE: An example using neighbormap
%          to examine the neighbors of
%          a vector-variable over a map
%---------------------------------------------------
% USAGE: neighbormap_d
%---------------------------------------------------


clear all;

load sids.data;
% variables are:
% col1 AREA    
% col2 PERIMETER
% col3 CNTY_   
% col4 CNTY_ID 
% col5 FIPSNO  
% col6 CRESS_ID    
% col7 BIR74   
% col8 SID74   
% col9 NWBIR74 
% col10 BIR79   
% col11 SID79   
% col12 NWBIR79

sid74=sids(:,8);
births74=sids(:,7);
sidspc = sid74./births74;
nobs = length(sid74);

load sids.poly;
carte = sids;

ind = ~isnan(carte(:,1));
nzip = find(ind);
dind = diff(nzip);
carti = carte(nzip,:);

latt = zeros(nobs,1);
long = zeros(nobs,1);
n = length(dind);
cnt = 1;
tvar = [];
for i=11:n;
indi = dind(i,1);
if indi == 1
tvar = [tvar
        carti(i,:)];
else
latt(cnt,1) = mean(tvar(:,1));
long(cnt,1) = mean(tvar(:,2));
cnt = cnt+1;
tvar = [];
end;
end;
latt(cnt,1) = mean(tvar(:,1));
long(cnt,1) = mean(tvar(:,2));

W = make_neighborsw(latt,long,4);

neighbormap(latt,long,sidspc,W,carte,[],1); % using points

