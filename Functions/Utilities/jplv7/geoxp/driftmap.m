function driftmap(long,lat,variable,nl,nc,interpol,varargin)
% PURPOSE: This function adds a grid to the map and for each rectangle of the grid computes
% the mean of the spatial units included in this part.The means and Medians are also computed for each row and each column
% and plotted on the side. 
%------------------------------------------------------------------------
% USAGE: driftmap(long,lat,variable,nl,nc,interpol,theta,carte,label)
%   where : lat = n x 1 vector of coordinates on the second axis
%           long = n x 1 vector of coordinates on the first axis
%           variable = n x 1 vector of the variable to study
%           nl = number of rows of the grid.
%           mc = number of columns of the grid
%           interpol: * interpol=1 : means and medians are linearly interpolated
%                     * interpol=0 : means and medians are not interpolated
%           theta = optionnal parameter giving the angle of rotation of the map (in degree)
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%------------------------------------------------------------------------
% uses rotation.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr

close all;
H=figure;
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
theta=0;
c=0;
name=inputname(3);
% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        theta=varargin{1};
    end;
    if  t==2 & ~isempty(varargin{2})
        carte=varargin{2};
        c=1;
    end;
end;
%%%%%%%%%%%%%%%%%%%%%
% rotation of the map
ncoord=rotation([long,lat],theta);
if c==1
    ncarte=rotation(carte,theta);
end;
nlong=ncoord(:,1);
nlat=ncoord(:,2);
%%%%%%%%%%%%%%%%%%%

% creation of the grid
gridx=[floor(min(nlong)):(ceil(max(nlong))-floor(min(nlong)))/nc:ceil(max(nlong))];
gridy=[ceil(max(nlat)):-(ceil(max(nlat))-floor(min(nlat)))/nl:floor(min(nlat))];
milx=gridx+(gridx(2)-gridx(1))/4;
milx=milx(1:end-1);
mily=gridy-(gridy(1)-gridy(2))/2;
mily=mily(1:end-1);
%%%%%%%%%%%%%%%%%%%%%%%

M=zeros(nl,nc);
C=zeros(nl,nc);
MedL=cell(nl,1);
MedC=cell(nc,1);
for i=1:length(nlat)
    Xn=sort([gridx,nlong(i)]);
    Yn=fliplr(sort([gridy,nlat(i)]));
    I=find(Yn==nlat(i))-1;
    I=I(1);
    J=find(Xn==nlong(i))-1;
    J=J(1);
    M(I,J)=M(I,J)+variable(i);
    C(I,J)=C(I,J)+1;
    MedL{I}=[MedL{I},variable(i)];
    MedC{J}=[MedC{J},variable(i)];
end;
K=find(C==0);
C(K)=0.5;
Moy=M./C;
C(K)=0;
Mtex=num2str(Moy(:),'%0.2f');

% trace the main graph

Main=subplot(2,2,1);
plot(nlong,nlat,'b.');
hold on;
if c==1
    plot(ncarte(:,1),ncarte(:,2),'r');
end;
lx=line([gridx;gridx],[repmat(gridy(1),1,length(gridx));repmat(gridy(end),1,length(gridx))]);
set(lx,'Color','red');
ly=line([repmat(gridx(1),1,length(gridy));repmat(gridx(end),1,length(gridy))],[gridy;gridy]);
set(ly,'Color','red');
axis equal;
[X,Y]=meshgrid(milx,mily);
%Y=flipud(Y);
%text(X(:),Y(:),Mtex);
Xlim1=get(Main,'XLim');
Ylim1=get(Main,'YLim');
Posmain=get(Main,'Position');
%%%%%%%%%%%%%%%%%%%%%%%

Mligne=sum(M')./(sum(C')+(sum(C')==0));
Mll=mean(Moy');
Mcol=sum(M)./(sum(C)+(sum(C)==0));
Mcc=mean(Moy);
for k=1:nl
    if ~isempty(MedL{k})
        Medlig(k)=median(MedL{k});
    end;
end;
for k=1:nc
    if ~isempty(MedC{k})
        Medcol(k)=median(MedC{k});
    end;
end;

% trace the right graph
Right=subplot(2,2,2);
if interpol==1
    plot(Mligne,mily,'b');
    hold on;
    plot(Medlig,mily,'r');
    hold off;
else
    plot(Mligne,mily,'b.');
    hold on;
    plot(Medlig,mily,'r.');
    hold off;
end;
Posright=get(Right,'Position');
set(Right,'Ylim',Ylim1);
set(Right,'Xlim',[floor(min(min(Mligne),min(Medlig))),ceil(max(max(Mligne),max(Medlig)))]);
set(Right,'Position',[Posright(1) Posright(2) Posright(3) Posmain(4)]);
set(Right,'PlotBoxAspectRatiomode','manual');
set(Right,'PlotBoxAspectRatio',get(Main,'PlotBoxAspectRatio'));
xlabel(name);
%%%%%%%%%%%%%%%%%%%%%%

% trace the bottom graph
Bottom=subplot(2,2,3);
if interpol==1
    plot(milx,Mcol,'b');
    hold on;
    plot(milx,Medcol,'r');
    hold off;
else
    plot(milx,Mcol,'b.');
    hold on;
    plot(milx,Medcol,'r.');
    hold off;
end;
Posbottom=get(Bottom,'Position');
set(Bottom,'Xlim',Xlim1);
set(Bottom,'Ylim',[floor(min(min(Mcol),min(Medcol))),ceil(max(max(Mcol),max(Medcol)))]);
set(Bottom,'Position',[Posbottom(1) Posbottom(2) Posmain(3) Posbottom(4)]);
set(Bottom,'PlotBoxAspectRatiomode','manual');
set(Bottom,'PlotBoxAspectRatio',get(Main,'PlotBoxAspectRatio'));
ylabel(name);
%%%%%%%%%%%%%%%%%%%%%%

% Trace the legend
leg=subplot(2,2,4);
px=[-1;1];
py=[0;0];
ax=[0;0];
ay=[-1;1];
b1x=[0;-0.1];
b1y=[1;0.9];
b2x=[0;0.1];
b2y=[1;0.9];
Tx=-0.025;
Ty=1.05;
CC=rotation([px,py],theta);
CC2=rotation([ax,ay],theta);
CC3=rotation([b1x,b1y],theta);
CC4=rotation([b2x,b2y],theta);
CC5=rotation([Tx,Ty],theta);
line(CC(:,1),CC(:,2),'Color','Black');
line(CC2(:,1),CC2(:,2),'Color','Black');
line(CC3(:,1),CC3(:,2),'Color','Black');
line(CC4(:,1),CC4(:,2),'Color','Black');
text(CC5(1),CC5(2),'N');
axis equal;
set(leg,'visible','off');
if interpol==1
    line([-0.75;-0.25],[1.5;1.5],'Color','blue');   
    line([-0.75;-0.25],[1.25;1.25],'Color','red');  
else
    hold on;
    plot(-0.25,1.5,'b.');
    plot(-0.25,1.25,'r.');
    hold off;  
end;
text(-0.2,1.5,'Moyenne');
text(-0.2,1.25,'Mediane');
%%%%%%%%%%%%%%%%%%%%%%%%